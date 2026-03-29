"""Director Workflow - orchestrates the discovery pipeline."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext
from app.agents.base.agent_step_runner import AgentStepRunner
from app.agents.content_asset_manager import ContentAssetManagerAgent
from app.agents.multilingual_copywriter import MultilingualCopywriterAgent
from app.agents.pricing_analyst import PricingAnalystAgent
from app.agents.product_selector import ProductSelectorAgent
from app.agents.risk_controller import RiskControllerAgent
from app.core.enums import StrategyRunStatus
from app.core.logging import get_logger
from app.db.models import StrategyRun
from app.services.candidate_conversion_service import CandidateConversionService

logger = get_logger(__name__)


class DirectorWorkflow:
    """Deterministic orchestrator for the discovery pipeline."""

    def __init__(self):
        self.product_selector = ProductSelectorAgent()
        self.pricing_analyst = PricingAnalystAgent()
        self.risk_controller = RiskControllerAgent()
        self.copywriter = MultilingualCopywriterAgent()
        self.content_asset_manager = ContentAssetManagerAgent()
        self.step_runner = AgentStepRunner()
        self.conversion_service = CandidateConversionService()

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

            # Step 5: Convert candidates to master products
            master_conversions = await self._convert_candidates_to_masters(
                candidate_ids=candidate_ids,
                db=db,
            )

            # Step 6: Generate base assets for converted masters (optional)
            asset_generation_results = []
            if master_conversions:
                asset_generation_results = await self._generate_base_assets(
                    conversions=master_conversions,
                    strategy_run=strategy_run,
                    db=db,
                )

            # Mark run as completed
            strategy_run.status = StrategyRunStatus.COMPLETED
            strategy_run.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "pipeline_completed",
                strategy_run_id=str(strategy_run_id),
                candidates_count=len(candidate_ids),
                masters_created=len(master_conversions),
                assets_generated=sum(r.get("assets_created", 0) for r in asset_generation_results),
            )

            return {
                "status": "completed",
                "candidates_count": len(candidate_ids),
                "masters_created": len(master_conversions),
                "steps": {
                    "product_selection": selector_result["output_data"],
                    "pricing_analysis": pricing_result["output_data"],
                    "risk_assessment": risk_result["output_data"],
                    "copywriting": copywriter_result["output_data"],
                    "master_conversion": [m.to_dict() for m in master_conversions],
                    "asset_generation": asset_generation_results,
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
        return await self.step_runner.execute_step(
            agent=agent,
            step_name=step_name,
            strategy_run=strategy_run,
            db=db,
            input_data=input_data,
        )

    async def _convert_candidates_to_masters(
        self,
        candidate_ids: list[str],
        db: AsyncSession,
    ) -> list:
        """Convert eligible candidates to master products.

        Validates each candidate and converts to master if eligible.
        Skips ineligible candidates with logging.

        Args:
            candidate_ids: List of candidate IDs to convert
            db: Database session

        Returns:
            List of CandidateConversionResult objects
        """
        conversions = []

        for candidate_id_str in candidate_ids:
            try:
                candidate_id = UUID(candidate_id_str)

                # Validate eligibility
                eligible, reason = await self.conversion_service.validate_conversion_eligibility(
                    candidate_id=candidate_id,
                    db=db,
                )

                if not eligible:
                    logger.warning(
                        "candidate_ineligible_for_master_conversion",
                        candidate_id=candidate_id_str,
                        reason=reason,
                    )
                    continue

                # Convert to master
                conversion = await self.conversion_service.convert_candidate_to_master(
                    candidate_id=candidate_id,
                    db=db,
                    auto_link_supplier=True,
                )
                conversions.append(conversion)

            except Exception as e:
                logger.error(
                    "candidate_conversion_failed",
                    candidate_id=candidate_id_str,
                    error=str(e),
                )
                continue

        return conversions

    async def _generate_base_assets(
        self,
        conversions: list,
        strategy_run: StrategyRun,
        db: AsyncSession,
    ) -> list[dict]:
        """Generate base assets for converted masters.

        Args:
            conversions: List of CandidateConversionResult objects
            strategy_run: Strategy run context
            db: Database session

        Returns:
            List of asset generation results
        """
        asset_results = []

        for conversion in conversions:
            try:
                # Create context for content asset manager
                context = AgentContext(
                    strategy_run_id=strategy_run.id,
                    db=db,
                    input_data={
                        "action": "generate_base_assets",
                        "variant_id": str(conversion.product_variant_id),
                        "asset_types": ["main_image"],
                        "styles": ["minimalist"],
                        "generate_count": 1,
                    },
                )

                result = await self.content_asset_manager.execute(context)

                asset_results.append({
                    "variant_id": str(conversion.product_variant_id),
                    "success": result.success,
                    "assets_created": result.output_data.get("assets_created", 0) if result.success else 0,
                    "error": result.error_message if not result.success else None,
                })

            except Exception as e:
                logger.error(
                    "asset_generation_failed",
                    variant_id=str(conversion.product_variant_id),
                    error=str(e),
                )
                asset_results.append({
                    "variant_id": str(conversion.product_variant_id),
                    "success": False,
                    "assets_created": 0,
                    "error": str(e),
                })

        return asset_results

