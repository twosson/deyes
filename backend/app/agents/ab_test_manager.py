"""AB Test Manager Agent.

This agent orchestrates A/B test experiment lifecycle:
- Creating and activating experiments
- Getting experiment summaries
- Selecting winners (automatic or manual)
- Promoting winners to main images
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.core.enums import TargetPlatform
from app.db.models import Experiment
from app.services.experiment_service import ExperimentService


class ABTestManagerAgent(BaseAgent):
    """Agent for managing A/B test experiments.

    Supported operations:
    - create_and_activate: Create and activate a new experiment
    - get_summary: Get experiment performance summary
    - select_winner: Automatically select the best-performing variant
    - set_winner: Manually set the winning variant
    - promote_winner: Promote the winning variant to main image
    """

    def __init__(self, experiment_service: ExperimentService | None = None):
        super().__init__("ab_test_manager")
        self.experiment_service = experiment_service or ExperimentService()

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute an AB test lifecycle operation."""
        try:
            operation = context.input_data.get("operation")
            if not operation:
                return AgentResult(
                    success=False,
                    output_data={},
                    error_message="Missing required parameter: operation",
                )

            if operation == "create_and_activate":
                return await self._create_and_activate(context)
            if operation == "get_summary":
                return await self._get_summary(context)
            if operation == "select_winner":
                return await self._select_winner(context)
            if operation == "set_winner":
                return await self._set_winner(context)
            if operation == "promote_winner":
                return await self._promote_winner(context)

            return AgentResult(
                success=False,
                output_data={},
                error_message=f"Unsupported operation: {operation}",
            )

        except Exception as e:
            return await self._handle_error(e, context)

    async def _create_and_activate(self, context: AgentContext) -> AgentResult:
        """Create and activate a new experiment."""
        try:
            candidate_product_id = UUID(context.input_data["candidate_product_id"])
            name = context.input_data.get("name") or f"Experiment for {candidate_product_id}"
            metric_goal = context.input_data.get("metric_goal", "ctr")
            target_platform_value = context.input_data.get("target_platform")
            region = context.input_data.get("region")
            notes = context.input_data.get("notes")
            metadata = context.input_data.get("metadata")

            target_platform = (
                TargetPlatform(target_platform_value) if target_platform_value else None
            )

            experiment = await self.experiment_service.create_experiment(
                context.db,
                candidate_product_id=candidate_product_id,
                name=name,
                metric_goal=metric_goal,
                target_platform=target_platform,
                region=region,
                notes=notes,
                metadata=metadata,
            )
            experiment = await self.experiment_service.activate_experiment(
                context.db,
                experiment_id=experiment.id,
            )
            variants = await self.experiment_service.get_experiment_variants(
                context.db,
                experiment_id=experiment.id,
            )

            await context.db.commit()

            return AgentResult(
                success=True,
                output_data={
                    "operation": "create_and_activate",
                    "experiment_id": str(experiment.id),
                    "candidate_product_id": str(candidate_product_id),
                    "status": experiment.status.value,
                    "metric_goal": experiment.metric_goal,
                    "variant_count": len(variants),
                },
            )
        except Exception as e:
            await context.db.rollback()
            return await self._handle_error(e, context)

    async def _get_summary(self, context: AgentContext) -> AgentResult:
        """Get experiment performance summary."""
        try:
            experiment_id = UUID(context.input_data["experiment_id"])
            start_date = self._parse_date(context.input_data.get("start_date"))
            end_date = self._parse_date(context.input_data.get("end_date"))

            summary = await self.experiment_service.get_experiment_summary(
                context.db,
                experiment_id=experiment_id,
                start_date=start_date,
                end_date=end_date,
            )

            return AgentResult(
                success=True,
                output_data={
                    "operation": "get_summary",
                    **summary,
                },
            )
        except Exception as e:
            return await self._handle_error(e, context)

    async def _select_winner(self, context: AgentContext) -> AgentResult:
        """Automatically select the best-performing variant."""
        try:
            experiment_id = UUID(context.input_data["experiment_id"])
            min_impressions = context.input_data.get("min_impressions", 100)
            promote_on_selection = context.input_data.get("promote_on_selection", False)

            winner_variant_group = await self.experiment_service.select_winner(
                context.db,
                experiment_id=experiment_id,
                min_impressions=min_impressions,
            )

            promotion_applied = False
            promoted_listing_ids: list[str] = []
            if winner_variant_group and promote_on_selection:
                promotion_result = await self.experiment_service.promote_winner(
                    context.db,
                    experiment_id=experiment_id,
                )
                promotion_applied = True
                promoted_listing_ids = promotion_result["promoted_listing_ids"]

            experiment = await context.db.get(Experiment, experiment_id)
            await context.db.commit()

            return AgentResult(
                success=True,
                output_data={
                    "operation": "select_winner",
                    "experiment_id": str(experiment_id),
                    "status": experiment.status.value if experiment else "unknown",
                    "winner_variant_group": winner_variant_group,
                    "promotion_applied": promotion_applied,
                    "promoted_listing_ids": promoted_listing_ids,
                },
            )
        except Exception as e:
            await context.db.rollback()
            return await self._handle_error(e, context)

    async def _set_winner(self, context: AgentContext) -> AgentResult:
        """Manually set the winning variant."""
        try:
            experiment_id = UUID(context.input_data["experiment_id"])
            winner_variant_group = context.input_data["winner_variant_group"]
            promote_on_selection = context.input_data.get("promote_on_selection", False)

            experiment = await self.experiment_service.set_winner(
                context.db,
                experiment_id=experiment_id,
                winner_variant_group=winner_variant_group,
            )

            promotion_applied = False
            promoted_listing_ids: list[str] = []
            if promote_on_selection:
                promotion_result = await self.experiment_service.promote_winner(
                    context.db,
                    experiment_id=experiment_id,
                )
                promotion_applied = True
                promoted_listing_ids = promotion_result["promoted_listing_ids"]

            await context.db.commit()

            return AgentResult(
                success=True,
                output_data={
                    "operation": "set_winner",
                    "experiment_id": str(experiment_id),
                    "status": experiment.status.value,
                    "winner_variant_group": winner_variant_group,
                    "promotion_applied": promotion_applied,
                    "promoted_listing_ids": promoted_listing_ids,
                },
            )
        except Exception as e:
            await context.db.rollback()
            return await self._handle_error(e, context)

    async def _promote_winner(self, context: AgentContext) -> AgentResult:
        """Promote the winning variant to main image."""
        try:
            experiment_id = UUID(context.input_data["experiment_id"])
            listing_ids_input = context.input_data.get("listing_ids")
            listing_ids = [UUID(listing_id) for listing_id in listing_ids_input] if listing_ids_input else None

            result = await self.experiment_service.promote_winner(
                context.db,
                experiment_id=experiment_id,
                listing_ids=listing_ids,
            )
            await context.db.commit()

            return AgentResult(
                success=True,
                output_data={
                    "operation": "promote_winner",
                    "experiment_id": str(experiment_id),
                    **result,
                },
            )
        except Exception as e:
            await context.db.rollback()
            return await self._handle_error(e, context)

    def _parse_date(self, value: str | None) -> date | None:
        """Parse an ISO date string when provided."""
        if not value:
            return None
        return date.fromisoformat(value)
