"""Risk Controller Agent."""
from uuid import UUID, uuid4

from sqlalchemy import select

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.core.enums import CandidateStatus, RiskDecision
from app.db.models import CandidateProduct, RiskAssessment
from app.services.risk_rules import RiskRulesEngine


class RiskControllerAgent(BaseAgent):
    """Agent for IP infringement and compliance screening."""

    def __init__(self, risk_engine: RiskRulesEngine = None):
        super().__init__("risk_controller")
        self.risk_engine = risk_engine or RiskRulesEngine()

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute risk assessment."""
        try:
            candidate_ids = context.input_data.get("candidate_ids", [])

            if not candidate_ids:
                return AgentResult(
                    success=True,
                    output_data={"assessed_count": 0, "passed_count": 0, "rejected_count": 0},
                )

            assessed_count = 0
            passed_count = 0
            rejected_count = 0

            for candidate_id_str in candidate_ids:
                candidate_id = UUID(candidate_id_str)

                # Fetch candidate
                result = await context.db.execute(
                    select(CandidateProduct).where(CandidateProduct.id == candidate_id)
                )
                candidate = result.scalar_one_or_none()

                if not candidate:
                    self.logger.warning("candidate_not_found", candidate_id=candidate_id_str)
                    continue

                # Prepare product data for risk assessment
                product_data = {
                    "title": candidate.title,
                    "category": candidate.category,
                    "platform_price": float(candidate.platform_price)
                    if candidate.platform_price
                    else None,
                }

                # Run risk assessment
                risk_result = self.risk_engine.assess(product_data)

                # Create risk assessment record
                assessment = RiskAssessment(
                    id=uuid4(),
                    candidate_product_id=candidate_id,
                    score=risk_result.score,
                    decision=risk_result.decision,
                    rule_hits={"hits": risk_result.rule_hits},
                    llm_notes=None,  # Optional LLM enrichment can be added later
                )
                context.db.add(assessment)

                # Update candidate status
                if risk_result.decision == RiskDecision.REJECT:
                    candidate.status = CandidateStatus.REJECTED
                    rejected_count += 1
                else:
                    candidate.status = CandidateStatus.RISK_ASSESSED
                    passed_count += 1

                assessed_count += 1

            await context.db.commit()

            self.logger.info(
                "risk_assessments_completed",
                assessed_count=assessed_count,
                passed_count=passed_count,
                rejected_count=rejected_count,
                strategy_run_id=str(context.strategy_run_id),
            )

            return AgentResult(
                success=True,
                output_data={
                    "assessed_count": assessed_count,
                    "passed_count": passed_count,
                    "rejected_count": rejected_count,
                },
            )

        except Exception as e:
            await context.db.rollback()
            return await self._handle_error(e, context)
