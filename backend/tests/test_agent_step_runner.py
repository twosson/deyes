"""Tests for shared agent step runner."""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.agents.base.agent_step_runner import AgentStepRunner
from app.core.enums import (
    AgentRunStatus,
    SourcePlatform,
    StrategyRunStatus,
    TriggerType,
)
from app.db.models import AgentRun, RunEvent, StrategyRun


class _StaticAgent(BaseAgent):
    """Test agent that returns a fixed result."""

    def __init__(self, name: str, result: AgentResult):
        super().__init__(name)
        self.result = result

    async def execute(self, context: AgentContext) -> AgentResult:
        return self.result


async def _create_strategy_run(db_session: AsyncSession) -> StrategyRun:
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.RUNNING,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()
    return strategy_run


@pytest.mark.asyncio
async def test_execute_step_records_agent_run_and_events_on_success(db_session: AsyncSession):
    """AgentStepRunner should create AgentRun and RunEvents for successful execution."""
    strategy_run = await _create_strategy_run(db_session)
    agent = _StaticAgent(
        "test_agent",
        AgentResult(success=True, output_data={"result": "ok"}),
    )
    runner = AgentStepRunner()

    result = await runner.execute_step(
        agent=agent,
        step_name="test_step",
        strategy_run=strategy_run,
        db=db_session,
        input_data={"input": "value"},
    )

    assert result["success"] is True
    assert result["output_data"] == {"result": "ok"}
    assert result["error_message"] is None

    stmt = select(AgentRun).where(AgentRun.strategy_run_id == strategy_run.id)
    agent_runs = list((await db_session.execute(stmt)).scalars().all())
    assert len(agent_runs) == 1

    agent_run = agent_runs[0]
    assert agent_run.step_name == "test_step"
    assert agent_run.agent_name == "test_agent"
    assert agent_run.status == AgentRunStatus.COMPLETED
    assert agent_run.input_data == {"input": "value"}
    assert agent_run.output_data == {"result": "ok"}
    assert agent_run.error_message is None
    assert agent_run.latency_ms is not None
    assert agent_run.latency_ms >= 0

    event_stmt = select(RunEvent).where(RunEvent.agent_run_id == agent_run.id)
    events = list((await db_session.execute(event_stmt)).scalars().all())
    assert len(events) == 2

    started_event = next(e for e in events if "started" in e.event_type)
    completed_event = next(e for e in events if "completed" in e.event_type)

    assert started_event.event_type == "agent.test_step.started"
    assert started_event.event_payload == {"agent": "test_agent"}

    assert completed_event.event_type == "agent.test_step.completed"
    assert completed_event.event_payload["agent"] == "test_agent"
    assert completed_event.event_payload["success"] is True
    assert completed_event.event_payload["latency_ms"] == agent_run.latency_ms


@pytest.mark.asyncio
async def test_execute_step_records_failure_when_agent_returns_error(db_session: AsyncSession):
    """AgentStepRunner should mark AgentRun as FAILED when agent returns failure."""
    strategy_run = await _create_strategy_run(db_session)
    agent = _StaticAgent(
        "failing_agent",
        AgentResult(success=False, output_data={}, error_message="Agent failed"),
    )
    runner = AgentStepRunner()

    result = await runner.execute_step(
        agent=agent,
        step_name="failing_step",
        strategy_run=strategy_run,
        db=db_session,
        input_data={},
    )

    assert result["success"] is False
    assert result["error_message"] == "Agent failed"

    stmt = select(AgentRun).where(AgentRun.strategy_run_id == strategy_run.id)
    agent_runs = list((await db_session.execute(stmt)).scalars().all())
    assert len(agent_runs) == 1

    agent_run = agent_runs[0]
    assert agent_run.status == AgentRunStatus.FAILED
    assert agent_run.error_message == "Agent failed"


@pytest.mark.asyncio
async def test_execute_step_records_failure_and_rolls_back_on_exception(db_session: AsyncSession):
    """AgentStepRunner should rollback and mark AgentRun as FAILED on exception."""

    class _ExceptionAgent(BaseAgent):
        async def execute(self, context: AgentContext) -> AgentResult:
            raise RuntimeError("Unexpected error")

    strategy_run = await _create_strategy_run(db_session)
    agent = _ExceptionAgent("exception_agent")
    runner = AgentStepRunner()

    with pytest.raises(RuntimeError, match="Unexpected error"):
        await runner.execute_step(
            agent=agent,
            step_name="exception_step",
            strategy_run=strategy_run,
            db=db_session,
            input_data={},
        )

    stmt = select(AgentRun).where(AgentRun.strategy_run_id == strategy_run.id)
    agent_runs = list((await db_session.execute(stmt)).scalars().all())
    assert len(agent_runs) == 1

    agent_run = agent_runs[0]
    assert agent_run.status == AgentRunStatus.FAILED
    assert agent_run.error_message == "Unexpected error"
    assert agent_run.completed_at is not None
