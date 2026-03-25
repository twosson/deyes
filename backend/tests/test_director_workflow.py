"""Tests for DirectorWorkflow orchestration."""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.agents.director_workflow import DirectorWorkflow
from app.core.enums import (
    AgentRunStatus,
    SourcePlatform,
    StrategyRunStatus,
    TriggerType,
)
from app.db.models import AgentRun, RunEvent, StrategyRun


class _MockAgent(BaseAgent):
    """Mock agent for testing."""

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
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()
    return strategy_run


async def _get_agent_runs(db_session: AsyncSession, *, strategy_run_id) -> list[AgentRun]:
    stmt = select(AgentRun).where(AgentRun.strategy_run_id == strategy_run_id)
    return list((await db_session.execute(stmt)).scalars().all())


async def _get_agent_events(db_session: AsyncSession, *, agent_run_id) -> list[RunEvent]:
    stmt = select(RunEvent).where(RunEvent.agent_run_id == agent_run_id)
    return list((await db_session.execute(stmt)).scalars().all())


@pytest.mark.asyncio
async def test_execute_pipeline_runs_all_four_steps(db_session: AsyncSession):
    """DirectorWorkflow should execute all 4 steps in sequence."""
    strategy_run = await _create_strategy_run(db_session)
    workflow = DirectorWorkflow()

    # Mock all agents to return success
    workflow.product_selector = _MockAgent(
        "product_selector",
        AgentResult(success=True, output_data={"candidate_ids": [str(uuid4()), str(uuid4())]}),
    )
    workflow.pricing_analyst = _MockAgent(
        "pricing_analyst",
        AgentResult(success=True, output_data={"pricing_completed": True}),
    )
    workflow.risk_controller = _MockAgent(
        "risk_controller",
        AgentResult(success=True, output_data={"risk_assessment_completed": True}),
    )
    workflow.copywriter = _MockAgent(
        "copywriter",
        AgentResult(success=True, output_data={"copywriting_completed": True}),
    )

    result = await workflow.execute_pipeline(strategy_run_id=strategy_run.id, db=db_session)

    assert result["status"] == "completed"
    assert result["candidates_count"] == 2
    assert "steps" in result
    assert "product_selection" in result["steps"]
    assert "pricing_analysis" in result["steps"]
    assert "risk_assessment" in result["steps"]
    assert "copywriting" in result["steps"]


@pytest.mark.asyncio
async def test_execute_pipeline_creates_agent_runs_and_events(db_session: AsyncSession):
    """DirectorWorkflow should create AgentRun and RunEvent records for each step."""
    strategy_run = await _create_strategy_run(db_session)
    workflow = DirectorWorkflow()

    workflow.product_selector = _MockAgent(
        "product_selector",
        AgentResult(success=True, output_data={"candidate_ids": [str(uuid4())]}),
    )
    workflow.pricing_analyst = _MockAgent(
        "pricing_analyst",
        AgentResult(success=True, output_data={"pricing_completed": True}),
    )
    workflow.risk_controller = _MockAgent(
        "risk_controller",
        AgentResult(success=True, output_data={"risk_assessment_completed": True}),
    )
    workflow.copywriter = _MockAgent(
        "copywriter",
        AgentResult(success=True, output_data={"copywriting_completed": True}),
    )

    await workflow.execute_pipeline(strategy_run_id=strategy_run.id, db=db_session)

    agent_runs = await _get_agent_runs(db_session, strategy_run_id=strategy_run.id)
    assert len(agent_runs) == 4

    step_names = {agent_run.step_name for agent_run in agent_runs}
    assert step_names == {"product_selection", "pricing_analysis", "risk_assessment", "copywriting"}

    for agent_run in agent_runs:
        assert agent_run.status == AgentRunStatus.COMPLETED
        events = await _get_agent_events(db_session, agent_run_id=agent_run.id)
        assert len(events) == 2
        event_types = {event.event_type for event in events}
        assert f"agent.{agent_run.step_name}.started" in event_types
        assert f"agent.{agent_run.step_name}.completed" in event_types


@pytest.mark.asyncio
async def test_execute_pipeline_records_latency(db_session: AsyncSession):
    """DirectorWorkflow should record latency_ms for each AgentRun."""
    strategy_run = await _create_strategy_run(db_session)
    workflow = DirectorWorkflow()

    workflow.product_selector = _MockAgent(
        "product_selector",
        AgentResult(success=True, output_data={"candidate_ids": [str(uuid4())]}),
    )
    workflow.pricing_analyst = _MockAgent(
        "pricing_analyst",
        AgentResult(success=True, output_data={"pricing_completed": True}),
    )
    workflow.risk_controller = _MockAgent(
        "risk_controller",
        AgentResult(success=True, output_data={"risk_assessment_completed": True}),
    )
    workflow.copywriter = _MockAgent(
        "copywriter",
        AgentResult(success=True, output_data={"copywriting_completed": True}),
    )

    await workflow.execute_pipeline(strategy_run_id=strategy_run.id, db=db_session)

    agent_runs = await _get_agent_runs(db_session, strategy_run_id=strategy_run.id)
    for agent_run in agent_runs:
        assert agent_run.latency_ms is not None
        assert agent_run.latency_ms >= 0


@pytest.mark.asyncio
async def test_execute_pipeline_handles_step_failure(db_session: AsyncSession):
    """DirectorWorkflow should handle step failure and mark StrategyRun as FAILED."""
    strategy_run = await _create_strategy_run(db_session)
    workflow = DirectorWorkflow()

    workflow.product_selector = _MockAgent(
        "product_selector",
        AgentResult(success=True, output_data={"candidate_ids": [str(uuid4())]}),
    )
    workflow.pricing_analyst = _MockAgent(
        "pricing_analyst",
        AgentResult(success=False, output_data={}, error_message="Pricing failed"),
    )

    with pytest.raises(Exception, match="Pricing analysis failed"):
        await workflow.execute_pipeline(strategy_run_id=strategy_run.id, db=db_session)

    await db_session.refresh(strategy_run)
    assert strategy_run.status == StrategyRunStatus.FAILED
    assert strategy_run.completed_at is not None


@pytest.mark.asyncio
async def test_execute_pipeline_no_candidates_returns_early(db_session: AsyncSession):
    """DirectorWorkflow should return early when product_selector returns no candidates."""
    strategy_run = await _create_strategy_run(db_session)
    workflow = DirectorWorkflow()

    workflow.product_selector = _MockAgent(
        "product_selector",
        AgentResult(success=True, output_data={"candidate_ids": []}),
    )

    result = await workflow.execute_pipeline(strategy_run_id=strategy_run.id, db=db_session)

    assert result["status"] == "completed"
    assert result["candidates_count"] == 0

    await db_session.refresh(strategy_run)
    assert strategy_run.status == StrategyRunStatus.COMPLETED

    agent_runs = await _get_agent_runs(db_session, strategy_run_id=strategy_run.id)
    assert len(agent_runs) == 1
    assert agent_runs[0].step_name == "product_selection"


@pytest.mark.asyncio
async def test_execute_pipeline_empty_candidates_no_pricing(db_session: AsyncSession):
    """DirectorWorkflow should not execute subsequent steps when candidate_ids is empty."""
    strategy_run = await _create_strategy_run(db_session)
    workflow = DirectorWorkflow()

    workflow.product_selector = _MockAgent(
        "product_selector",
        AgentResult(success=True, output_data={"candidate_ids": []}),
    )

    result = await workflow.execute_pipeline(strategy_run_id=strategy_run.id, db=db_session)

    assert result["status"] == "completed"
    assert result["candidates_count"] == 0

    agent_runs = await _get_agent_runs(db_session, strategy_run_id=strategy_run.id)
    step_names = {agent_run.step_name for agent_run in agent_runs}
    assert "pricing_analysis" not in step_names
    assert "risk_assessment" not in step_names
    assert "copywriting" not in step_names
