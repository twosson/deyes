"""Multilingual Copywriter Agent."""
from uuid import UUID, uuid4

from sqlalchemy import select

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.clients.sglang import SGLangClient
from app.core.enums import CandidateStatus, RiskDecision
from app.db.models import CandidateProduct, ListingDraft, RiskAssessment
from app.services.copywriter_service import CopywriterService


class MultilingualCopywriterAgent(BaseAgent):
    """Agent for generating multilingual listing copy."""

    def __init__(self, copywriter_service: CopywriterService = None):
        super().__init__("multilingual_copywriter")
        self.copywriter_service = copywriter_service

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute copywriting."""
        try:
            candidate_ids = context.input_data.get("candidate_ids", [])
            target_languages = context.input_data.get("target_languages", ["en"])

            if not candidate_ids:
                return AgentResult(
                    success=True,
                    output_data={"processed_count": 0, "drafts_created": 0},
                )

            # Initialize copywriter service if not provided
            if not self.copywriter_service:
                sglang_client = SGLangClient()
                self.copywriter_service = CopywriterService(sglang_client)

            processed_count = 0
            drafts_created = 0

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

                # Check if candidate passed risk assessment
                risk_result = await context.db.execute(
                    select(RiskAssessment).where(
                        RiskAssessment.candidate_product_id == candidate_id
                    )
                )
                risk_assessment = risk_result.scalar_one_or_none()

                if risk_assessment and risk_assessment.decision == RiskDecision.REJECT:
                    self.logger.info(
                        "skipping_rejected_candidate",
                        candidate_id=candidate_id_str,
                    )
                    continue

                # Prepare product context
                product_context = {
                    "title": candidate.title,
                    "category": candidate.category,
                    "platform_price": float(candidate.platform_price)
                    if candidate.platform_price
                    else 0,
                    "key_features": [],  # Could be extracted from raw_payload
                }

                # Generate copy for each language
                for language in target_languages:
                    try:
                        copy = await self.copywriter_service.generate_listing_copy(
                            product_context=product_context,
                            language=language,
                        )

                        # Create listing draft record
                        draft = ListingDraft(
                            id=uuid4(),
                            candidate_product_id=candidate_id,
                            language=language,
                            title=copy.get("title", ""),
                            bullets=copy.get("bullets", []),
                            description=copy.get("description", ""),
                            seo_keywords=copy.get("seo_keywords", []),
                            status="generated",
                            prompt_version="v1.0",
                        )
                        context.db.add(draft)
                        drafts_created += 1

                    except Exception as e:
                        self.logger.error(
                            "copy_generation_failed",
                            candidate_id=candidate_id_str,
                            language=language,
                            error=str(e),
                        )
                        # Continue with other languages

                # Update candidate status
                candidate.status = CandidateStatus.COPY_GENERATED
                processed_count += 1

            await context.db.commit()

            self.logger.info(
                "copywriting_completed",
                processed_count=processed_count,
                drafts_created=drafts_created,
                strategy_run_id=str(context.strategy_run_id),
            )

            return AgentResult(
                success=True,
                output_data={
                    "processed_count": processed_count,
                    "drafts_created": drafts_created,
                },
            )

        except Exception as e:
            await context.db.rollback()
            return await self._handle_error(e, context)
