"""Auto Action Engine API routes."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PlatformListingStatus, TargetPlatform
from app.db.database import get_db
from app.db.models import PlatformListing
from app.services.auto_action_engine import AutoActionEngine

router = APIRouter(prefix="/auto-actions", tags=["auto-actions"])


# ============================================================================
# Schemas
# ============================================================================


class AutoPublishRequest(BaseModel):
    """Request to auto-publish a candidate.

    Note: recommendation_score, risk_score, and margin_percentage are deprecated
    and ignored by the server. These values are recomputed from source-of-truth
    data (PricingAssessment, RiskAssessment, CandidateProduct.normalized_attributes)
    to prevent client tampering. Fields are kept for backward compatibility.
    """

    candidate_id: UUID
    platform: TargetPlatform
    region: str = Field(..., min_length=2, max_length=10)
    price: Decimal = Field(..., gt=0)
    currency: str = Field(..., min_length=3, max_length=3)
    recommendation_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="DEPRECATED: Ignored by server, recomputed from DB. Kept for backward compatibility.",
    )
    risk_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="DEPRECATED: Ignored by server, recomputed from DB. Kept for backward compatibility.",
    )
    margin_percentage: Decimal = Field(
        ...,
        ge=0,
        le=100,
        description="DEPRECATED: Ignored by server, recomputed from DB. Kept for backward compatibility.",
    )


class ApprovalRequest(BaseModel):
    """Request to approve/reject a listing."""

    approved_by: str = Field(..., min_length=1, max_length=100)
    reason: Optional[str] = None


class PlatformListingResponse(BaseModel):
    """Platform listing response."""

    id: UUID
    candidate_product_id: UUID
    platform: TargetPlatform
    region: str
    price: Decimal
    currency: str
    status: PlatformListingStatus
    approval_required: bool
    approval_reason: Optional[str]
    platform_listing_id: Optional[str]
    platform_url: Optional[str]
    auto_action_metadata: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class PendingApprovalResponse(BaseModel):
    """Response for pending approval listings."""

    items: list[PlatformListingResponse]
    count: int


# ============================================================================
# Routes
# ============================================================================


@router.post("/publish", response_model=PlatformListingResponse)
async def auto_publish(
    request: AutoPublishRequest,
    db: AsyncSession = Depends(get_db),
):
    """Trigger auto-publish for a candidate.

    This endpoint creates a PlatformListing and either:
    1. Publishes it immediately if it meets auto-execute criteria
    2. Sets it to pending_approval if it requires human review

    Note:
        recommendation_score, risk_score, and margin_percentage from the request
        are deprecated and ignored. The server recomputes these values from
        source-of-truth data before evaluating approval boundaries.

    Args:
        request: Auto-publish request
        db: Database session

    Returns:
        Created PlatformListing
    """
    engine = AutoActionEngine(db)
    try:
        listing = await engine.auto_publish(
            candidate_id=request.candidate_id,
            platform=request.platform,
            region=request.region,
            price=request.price,
            currency=request.currency,
            recommendation_score=request.recommendation_score,
            risk_score=request.risk_score,
            margin_percentage=request.margin_percentage,
        )
        return listing
    finally:
        await engine.close()


@router.get("/pending-approval", response_model=PendingApprovalResponse)
async def get_pending_approval(
    platform: Optional[TargetPlatform] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get listings pending approval.

    Args:
        platform: Filter by platform (optional)
        limit: Max number of results
        db: Database session

    Returns:
        List of pending approval listings
    """
    stmt = (
        select(PlatformListing)
        .where(PlatformListing.status == PlatformListingStatus.PENDING_APPROVAL)
        .order_by(PlatformListing.created_at.desc())
        .limit(limit)
    )

    if platform:
        stmt = stmt.where(PlatformListing.platform == platform)

    result = await db.execute(stmt)
    listings = result.scalars().all()

    return PendingApprovalResponse(items=listings, count=len(listings))


@router.post("/approve/{listing_id}", response_model=PlatformListingResponse)
async def approve_listing(
    listing_id: UUID,
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending listing and publish it.

    Args:
        listing_id: Listing ID
        request: Approval request
        db: Database session

    Returns:
        Updated listing
    """
    engine = AutoActionEngine(db)
    try:
        listing = await engine.approve_listing(listing_id, request.approved_by)
        return listing
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        await engine.close()


@router.post("/reject/{listing_id}", response_model=PlatformListingResponse)
async def reject_listing(
    listing_id: UUID,
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending listing.

    Args:
        listing_id: Listing ID
        request: Rejection request (reason required)
        db: Database session

    Returns:
        Updated listing
    """
    if not request.reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")

    engine = AutoActionEngine(db)
    try:
        listing = await engine.reject_listing(listing_id, request.approved_by, request.reason)
        return listing
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        await engine.close()


@router.post("/reprice/{listing_id}")
async def auto_reprice(
    listing_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Trigger auto-reprice for a listing.

    This endpoint analyzes recent performance data and adjusts price
    based on ROI targets.

    Args:
        listing_id: Listing ID
        db: Database session

    Returns:
        Price history record if price was changed
    """
    engine = AutoActionEngine(db)
    try:
        price_history = await engine.auto_reprice(listing_id)
        if price_history:
            return {
                "success": True,
                "old_price": str(price_history.old_price),
                "new_price": str(price_history.new_price),
                "reason": price_history.reason,
            }
        return {"success": False, "message": "No price change needed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        await engine.close()


@router.post("/pause/{listing_id}")
async def auto_pause(
    listing_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Trigger auto-pause for a listing.

    This endpoint analyzes recent performance data and pauses the listing
    if ROI is below threshold for 7 days.

    Args:
        listing_id: Listing ID
        db: Database session

    Returns:
        Success status
    """
    engine = AutoActionEngine(db)
    try:
        paused = await engine.auto_pause(listing_id)
        return {"success": paused, "message": "Listing paused" if paused else "No pause needed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        await engine.close()


@router.post("/switch-asset/{listing_id}")
async def auto_asset_switch(
    listing_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Trigger auto-asset-switch for a listing.

    This endpoint analyzes asset performance and switches to a better-performing
    asset if current CTR is below platform average.

    Args:
        listing_id: Listing ID
        db: Database session

    Returns:
        Success status
    """
    engine = AutoActionEngine(db)
    try:
        switched = await engine.auto_asset_switch(listing_id)
        return {"success": switched, "message": "Asset switched" if switched else "No switch needed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        await engine.close()
