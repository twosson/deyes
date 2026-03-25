"""A/B test workflow orchestration."""
from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ab_test_manager import ABTestManagerAgent
from app.agents.base.agent_step_runner import AgentStepRunner
from app.db.models import CandidateProduct, Experiment, StrategyRun


class ABTestWorkflow:
    """Orchestrator for A/B test experiment operations."""

    def __init__(self):
        self.ab_test_manager = ABTestManagerAgent()
        self.step_runner = AgentStepRunner()

    async def execute_operation(
        self,
        db: AsyncSession,
        *,
        operation: str,
        candidate_product_id: UUID | None = None,
        experiment_id: UUID | None = None,
        **operation_params,
    ) -> dict:
        """Execute a single A/B test operation with observability."""
        strategy_run = await self._resolve_strategy_run(
            db,
            operation=operation,
            candidate_product_id=candidate_product_id,
            experiment_id=experiment_id,
        )

        input_data = {"operation": operation}
        if candidate_product_id is not None:
            input_data["candidate_product_id"] = str(candidate_product_id)
        if experiment_id is not None:
            input_data["experiment_id"] = str(experiment_id)

        for key, value in operation_params.items():
            input_data[key] = self._serialize_input_value(value)

        return await self.step_runner.execute_step(
            agent=self.ab_test_manager,
            step_name=f"ab_test_{operation}",
            strategy_run=strategy_run,
            db=db,
            input_data=input_data,
        )

    async def _resolve_strategy_run(
        self,
        db: AsyncSession,
        *,
        operation: str,
        candidate_product_id: UUID | None,
        experiment_id: UUID | None,
    ) -> StrategyRun:
        if operation == "create_and_activate":
            if candidate_product_id is None:
                raise ValueError("candidate_product_id required for create_and_activate")
            return await self._get_strategy_run_from_candidate(db, candidate_product_id)

        if experiment_id is not None:
            return await self._get_strategy_run_from_experiment(db, experiment_id)

        if candidate_product_id is not None:
            return await self._get_strategy_run_from_candidate(db, candidate_product_id)

        raise ValueError(f"experiment_id required for {operation}")

    async def _get_strategy_run_from_candidate(
        self,
        db: AsyncSession,
        candidate_product_id: UUID,
    ) -> StrategyRun:
        candidate = await db.get(CandidateProduct, candidate_product_id)
        if candidate is None:
            raise ValueError(f"Candidate not found: {candidate_product_id}")

        strategy_run = await db.get(StrategyRun, candidate.strategy_run_id)
        if strategy_run is None:
            raise ValueError(f"Strategy run not found: {candidate.strategy_run_id}")
        return strategy_run

    async def _get_strategy_run_from_experiment(
        self,
        db: AsyncSession,
        experiment_id: UUID,
    ) -> StrategyRun:
        experiment = await db.get(Experiment, experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment not found: {experiment_id}")

        candidate = await db.get(CandidateProduct, experiment.candidate_product_id)
        if candidate is None:
            raise ValueError(f"Candidate not found: {experiment.candidate_product_id}")

        strategy_run = await db.get(StrategyRun, candidate.strategy_run_id)
        if strategy_run is None:
            raise ValueError(f"Strategy run not found: {candidate.strategy_run_id}")
        return strategy_run

    def _serialize_input_value(self, value):
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, list):
            return [self._serialize_input_value(item) for item in value]
        return value
