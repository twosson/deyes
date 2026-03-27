"""Recommendation feedback schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import FeedbackAction


class CreateFeedbackRequest(BaseModel):
    """Request to create recommendation feedback."""

    action: FeedbackAction = Field(..., description="Feedback action: accepted, rejected, deferred")
    comment: Optional[str] = Field(None, description="Optional user comment")


class FeedbackResponse(BaseModel):
    """Recommendation feedback response."""

    id: UUID
    candidate_product_id: UUID
    action: FeedbackAction
    comment: Optional[str] = None
    metadata_: Optional[dict] = Field(None, alias="metadata")
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True
