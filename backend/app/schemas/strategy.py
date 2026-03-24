"""Strategy run schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import SourcePlatform, StrategyRunStatus, TriggerType


class CreateStrategyRunRequest(BaseModel):
    """Request to create a strategy run."""

    platform: SourcePlatform = Field(..., description="Source platform")
    region: Optional[str] = Field(
        None,
        description="Target region/country code (e.g., 'us', 'uk', 'de'). Determines site locale and proxy selection."
    )
    category: Optional[str] = Field(None, description="Product category")
    keywords: Optional[list[str]] = Field(None, description="Search keywords")
    price_min: Optional[Decimal] = Field(None, description="Minimum price")
    price_max: Optional[Decimal] = Field(None, description="Maximum price")
    target_languages: Optional[list[str]] = Field(
        default=["en"], description="Target languages for copy"
    )
    max_candidates: int = Field(default=10, description="Maximum candidates to discover")


class StrategyRunResponse(BaseModel):
    """Strategy run response."""

    run_id: UUID
    status: StrategyRunStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StrategyRunStatusResponse(BaseModel):
    """Strategy run status response."""

    run_id: UUID
    status: StrategyRunStatus
    current_step: Optional[str] = None
    progress: dict
    candidates_discovered: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
