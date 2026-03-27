"""Recommendation feedback service."""
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CandidateProduct, RecommendationFeedback, RunEvent


class RecommendationFeedbackService:
    """Service for managing recommendation feedback."""

    async def create_feedback(
        self,
        db: AsyncSession,
        candidate: CandidateProduct,
        action: str,
        comment: str | None = None,
        metadata: dict | None = None,
    ) -> RecommendationFeedback:
        """Create feedback for a recommendation candidate."""
        feedback = RecommendationFeedback(
            id=uuid4(),
            candidate_product_id=candidate.id,
            action=action,
            comment=comment,
            metadata_=metadata,
        )
        db.add(feedback)

        event = RunEvent(
            id=uuid4(),
            strategy_run_id=candidate.strategy_run_id,
            event_type="recommendation_feedback_created",
            event_payload={
                "candidate_product_id": str(candidate.id),
                "action": action,
                "comment": comment,
                "metadata": metadata,
            },
        )
        db.add(event)

        await db.commit()
        await db.refresh(feedback)
        return feedback
