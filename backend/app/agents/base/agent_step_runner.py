"""Reusable agent step execution with observability."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext, BaseAgent
from app.core.enums import AgentRunStatus
from app.core.logging import get_logger
from app.db.models import AgentRun, RunEvent, StrategyRun

logger = get_logger(__name__)


class AgentStepRunner:
    """Reusable agent step execution with observability.

    Wraps agent execution with AgentRun and RunEvent logging,
    preserving the observability patterns from DirectorWorkflow.
    """

    async def execute_step(
        self,
        agent: BaseAgent,
        step_name: str,
        strategy_run: StrategyRun,
        db: AsyncSession,
        input_data: dict,
    ) -> dict:
        """Execute agent step with AgentRun/RunEvent logging.

        Args:
            agent: The agent to execute
            step_name: Name of the step for logging
            strategy_run: The strategy run context
            db: Database session
            input_data: Input data for the agent

        Returns:
            dict with:
                - success: bool
                - output_data: dict
                - error_message: str | None
        """
        agent_run_id = uuid4()
        started_at = datetime.now(timezone.utc)
        # Extract strategy_run_id early to avoid ORM lazy load in exception handlers
        strategy_run_id = strategy_run.id

        # Create agent run record
        agent_run = AgentRun(
            id=agent_run_id,
            strategy_run_id=strategy_run_id,
            step_name=step_name,
            agent_name=agent.name,
            status=AgentRunStatus.RUNNING,
            input_data=input_data,
            started_at=started_at,
        )
        db.add(agent_run)

        # Create started event
        event = RunEvent(
            id=uuid4(),
            strategy_run_id=strategy_run_id,
            agent_run_id=agent_run_id,
            event_type=f"agent.{step_name}.started",
            event_payload={"agent": agent.name},
        )
        db.add(event)
        await db.commit()

        try:
            # Execute agent
            context = AgentContext(
                strategy_run_id=strategy_run_id,
                db=db,
                input_data=input_data,
            )
            result = await agent.execute(context)

            # Update agent run
            completed_at = datetime.now(timezone.utc)
            agent_run.status = (
                AgentRunStatus.COMPLETED if result.success else AgentRunStatus.FAILED
            )
            agent_run.output_data = result.output_data
            agent_run.error_message = result.error_message
            agent_run.completed_at = completed_at
            agent_run.latency_ms = int((completed_at - started_at).total_seconds() * 1000)

            # Create completion event
            completion_event = RunEvent(
                id=uuid4(),
                strategy_run_id=strategy_run_id,
                agent_run_id=agent_run_id,
                event_type=f"agent.{step_name}.completed",
                event_payload={
                    "agent": agent.name,
                    "success": result.success,
                    "latency_ms": agent_run.latency_ms,
                },
            )
            db.add(completion_event)
            await db.commit()

            return {
                "success": result.success,
                "output_data": result.output_data,
                "error_message": result.error_message,
            }

        except Exception as e:
            logger.error(
                "agent_step_failed",
                step_name=step_name,
                agent=agent.name,
                error=str(e),
            )
            # Rollback first to clear any pending transaction state
            await db.rollback()
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = str(e)
            agent_run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise
