"""Pricing Analyst Agent."""
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.core.enums import CandidateStatus
from app.db.models import CandidateProduct, PricingAssessment
from app.services.pricing_service import PricingService, SupplierPathInput


class PricingAnalystAgent(BaseAgent):
    """Agent for calculating profit margins and pricing."""

    def __init__(self, pricing_service: PricingService = None):
        super().__init__("pricing_analyst")
        self.pricing_service = pricing_service or PricingService()

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute pricing analysis."""
        try:
            candidate_ids = context.input_data.get("candidate_ids", [])

            if not candidate_ids:
                return AgentResult(
                    success=True,
                    output_data={"assessed_count": 0},
                )

            assessed_count = 0

            for candidate_id_str in candidate_ids:
                candidate_id = UUID(candidate_id_str)

                # Fetch candidate with supplier matches
                result = await context.db.execute(
                    select(CandidateProduct)
                    .where(CandidateProduct.id == candidate_id)
                    .options(selectinload(CandidateProduct.supplier_matches))
                )
                candidate = result.scalar_one_or_none()

                if not candidate:
                    self.logger.warning("candidate_not_found", candidate_id=candidate_id_str)
                    continue

                # Convert supplier matches to service input
                supplier_paths = [
                    SupplierPathInput(
                        id=str(match.id),
                        supplier_name=match.supplier_name,
                        supplier_sku=match.supplier_sku,
                        supplier_price=match.supplier_price,
                        moq=match.moq,
                        confidence_score=match.confidence_score,
                        raw_payload=match.raw_payload,
                    )
                    for match in candidate.supplier_matches
                ]

                if not supplier_paths:
                    self.logger.warning(
                        "no_supplier_matches_found",
                        candidate_id=candidate_id_str,
                    )
                    continue

                # Select best supplier path
                selection_result = self.pricing_service.select_best_supplier_path(supplier_paths)

                # Reset all supplier selected flags before applying the current selection result
                supplier_match_map = {str(match.id): match for match in candidate.supplier_matches}
                for match in candidate.supplier_matches:
                    match.selected = False

                if not selection_result.selected_path:
                    self.logger.warning(
                        "no_valid_supplier_price",
                        candidate_id=candidate_id_str,
                        competition_set_size=selection_result.competition_set_size,
                    )
                    continue

                if candidate.platform_price is None or candidate.platform_price <= 0:
                    self.logger.warning(
                        "invalid_platform_price",
                        candidate_id=candidate_id_str,
                        platform_price=float(candidate.platform_price)
                        if candidate.platform_price is not None
                        else None,
                    )
                    continue

                # Calculate pricing using selected supplier
                pricing_result = self.pricing_service.calculate_pricing(
                    supplier_price=selection_result.selected_path.supplier_price,
                    platform_price=candidate.platform_price,
                    platform=candidate.source_platform.value if candidate.source_platform else None,
                    category=candidate.category,
                )

                # Build explanation with supplier selection details
                explanation = pricing_result.to_dict()["explanation"]
                explanation["supplier_selection"] = selection_result.to_explanation()

                # Check if pricing assessment already exists (for idempotent reruns)
                existing_assessment_result = await context.db.execute(
                    select(PricingAssessment).where(
                        PricingAssessment.candidate_product_id == candidate_id
                    )
                )
                existing_assessment = existing_assessment_result.scalar_one_or_none()

                if existing_assessment:
                    # Update existing assessment
                    existing_assessment.estimated_shipping_cost = pricing_result.estimated_shipping_cost
                    existing_assessment.platform_commission_rate = pricing_result.platform_commission_rate
                    existing_assessment.payment_fee_rate = pricing_result.payment_fee_rate
                    existing_assessment.return_rate_assumption = pricing_result.return_rate_assumption
                    existing_assessment.total_cost = pricing_result.total_cost
                    existing_assessment.estimated_margin = pricing_result.estimated_margin
                    existing_assessment.margin_percentage = pricing_result.margin_percentage
                    existing_assessment.recommended_price = pricing_result.recommended_price
                    existing_assessment.profitability_decision = pricing_result.profitability_decision
                    existing_assessment.explanation = explanation
                else:
                    # Create new pricing assessment record
                    assessment = PricingAssessment(
                        id=uuid4(),
                        candidate_product_id=candidate_id,
                        estimated_shipping_cost=pricing_result.estimated_shipping_cost,
                        platform_commission_rate=pricing_result.platform_commission_rate,
                        payment_fee_rate=pricing_result.payment_fee_rate,
                        return_rate_assumption=pricing_result.return_rate_assumption,
                        total_cost=pricing_result.total_cost,
                        estimated_margin=pricing_result.estimated_margin,
                        margin_percentage=pricing_result.margin_percentage,
                        recommended_price=pricing_result.recommended_price,
                        profitability_decision=pricing_result.profitability_decision,
                        explanation=explanation,
                    )
                    context.db.add(assessment)

                # Update candidate status
                candidate.status = CandidateStatus.PRICED

                # Mark the selected supplier
                selected_match = supplier_match_map.get(selection_result.selected_path.id)
                if selected_match:
                    selected_match.selected = True

                assessed_count += 1

            await context.db.commit()

            self.logger.info(
                "pricing_assessments_completed",
                assessed_count=assessed_count,
                strategy_run_id=str(context.strategy_run_id),
            )

            return AgentResult(
                success=True,
                output_data={
                    "assessed_count": assessed_count,
                },
            )

        except Exception as e:
            await context.db.rollback()
            return await self._handle_error(e, context)
