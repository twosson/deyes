"""Director Workflow - orchestrates the discovery pipeline."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext
from app.agents.multilingual_copywriter import MultilingualCopywriterAgent
from app.agents.pricing_analyst import PricingAnalystAgent
from app.agents.product_selector import ProductSelectorAgent
from app.agents.risk_controller import RiskControllerAgent
from app.core.enums import AgentRunStatus, StrategyRunStatus
from app.core.logging import get_logger
from app.db.models import AgentRun, RunEvent, StrategyRun

logger = get_logger(__name__)


class DirectorWorkflow:
    """Deterministic orchestrator for the discovery pipeline."""

    def __init__(self):
        self.product_selector = ProductSelectorAgent()
        self.pricing_analyst = PricingAnalystAgent()
        self.risk_controller = RiskControllerAgent()
        self.copywriter = MultilingualCopywriterAgent()

    async def execute_pipeline(
        self,
        strategy_run_id: UUID,
        db: AsyncSession,
    ) -> dict:
        """Execute the full discovery pipeline."""
        logger.info("pipeline_started", strategy_run_id=str(strategy_run_id))

        # Fetch strategy run
        strategy_run = await db.get(StrategyRun, strategy_run_id)
        if not strategy_run:
            raise ValueError(f"Strategy run {strategy_run_id} not found")

        # Update status
        strategy_run.status = StrategyRunStatus.RUNNING
        strategy_run.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            # Step 1: Product Selection
            selector_result = await self._execute_agent_step(
                agent=self.product_selector,
                step_name="product_selection",
                strategy_run=strategy_run,
                db=db,
                input_data={
                    "platform": strategy_run.source_platform.value,
                    "region": strategy_run.region,
                    "category": strategy_run.category,
                    "keywords": strategy_run.keywords or [],
                    "price_min": float(strategy_run.price_min) if strategy_run.price_min else None,
                    "price_max": float(strategy_run.price_max) if strategy_run.price_max else None,
                    "max_candidates": strategy_run.max_candidates,
                },
            )

            if not selector_result["success"]:
                raise Exception(f"Product selection failed: {selector_result.get('error_message')}")

            candidate_ids = selector_result["output_data"].get("candidate_ids", [])

            if not candidate_ids:
                logger.warning("no_candidates_found", strategy_run_id=str(strategy_run_id))
                strategy_run.status = StrategyRunStatus.COMPLETED
                strategy_run.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return {"status": "completed", "candidates_count": 0}

            # Step 2: Pricing Analysis
            pricing_result = await self._execute_agent_step(
                agent=self.pricing_analyst,
                step_name="pricing_analysis",
                strategy_run=strategy_run,
                db=db,
                input_data={"candidate_ids": candidate_ids},
            )

            if not pricing_result["success"]:
                raise Exception(f"Pricing analysis failed: {pricing_result.get('error_message')}")

            # Step 3: Risk Assessment
            risk_result = await self._execute_agent_step(
                agent=self.risk_controller,
                step_name="risk_assessment",
                strategy_run=strategy_run,
                db=db,
                input_data={"candidate_ids": candidate_ids},
            )

            if not risk_result["success"]:
                raise Exception(f"Risk assessment failed: {risk_result.get('error_message')}")

            # Step 4: Multilingual Copywriting
            copywriter_result = await self._execute_agent_step(
                agent=self.copywriter,
                step_name="copywriting",
                strategy_run=strategy_run,
                db=db,
                input_data={
                    "candidate_ids": candidate_ids,
                    "target_languages": strategy_run.target_languages or ["en"],
                },
            )

            if not copywriter_result["success"]:
                raise Exception(f"Copywriting failed: {copywriter_result.get('error_message')}")

            # Mark run as completed
            strategy_run.status = StrategyRunStatus.COMPLETED
            strategy_run.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "pipeline_completed",
                strategy_run_id=str(strategy_run_id),
                candidates_count=len(candidate_ids),
            )

            return {
                "status": "completed",
                "candidates_count": len(candidate_ids),
                "steps": {
                    "product_selection": selector_result["output_data"],
                    "pricing_analysis": pricing_result["output_data"],
                    "risk_assessment": risk_result["output_data"],
                    "copywriting": copywriter_result["output_data"],
                },
            }

        except Exception as e:
            logger.error(
                "pipeline_failed",
                strategy_run_id=str(strategy_run_id),
                error=str(e),
            )
            # Rollback first to clear any pending transaction state
            await db.rollback()
            strategy_run.status = StrategyRunStatus.FAILED
            strategy_run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise

    async def _execute_agent_step(
        self,
        agent,
        step_name: str,
        strategy_run: StrategyRun,
        db: AsyncSession,
        input_data: dict,
    ) -> dict:
        """Execute a single agent step."""
        from uuid import uuid4

        agent_run_id = uuid4()
        started_at = datetime.now(timezone.utc)

        # Create agent run record
        agent_run = AgentRun(
            id=agent_run_id,
            strategy_run_id=strategy_run.id,
            step_name=step_name,
            agent_name=agent.name,
            status=AgentRunStatus.RUNNING,
            input_data=input_data,
            started_at=started_at,
        )
        db.add(agent_run)

        # Create event
        event = RunEvent(
            id=uuid4(),
            strategy_run_id=strategy_run.id,
            agent_run_id=agent_run_id,
            event_type=f"agent.{step_name}.started",
            event_payload={"agent": agent.name},
        )
        db.add(event)
        await db.commit()

        try:
            # Execute agent
            context = AgentContext(
                strategy_run_id=strategy_run.id,
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
                strategy_run_id=strategy_run.id,
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
