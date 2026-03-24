"""Platform Listing Management API endpoints.

Provides REST API for:
- Publishing products to platforms
- Listing platform listings
- Updating listings (price, inventory)
- Syncing inventory
- Managing listing status
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext
from app.agents.platform_publisher import PlatformPublisherAgent, PlatformSyncAgent
from app.core.enums import PlatformListingStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import CandidateProduct, PlatformListing
from app.db.session import get_db

logger = get_logger(__name__)
router = APIRouter(prefix="/platform-listings", tags=["platform-listings"])


# ============================================================================
# Request/Response Models
# ============================================================================


class PlatformConfig(BaseModel):
    """Platform configuration for publishing."""

    platform: str = Field(..., description="Platform name (temu, amazon, etc.)")
    region: str = Field(..., description="Region code (us, uk, de, etc.)")


class PublishRequest(BaseModel):
    """Request to publish product to platforms."""

    candidate_product_id: UUID = Field(..., description="Candidate product ID")
    target_platforms: list[PlatformConfig] = Field(
        ...,
        description="Target platforms and regions",
        examples=[[{"platform": "temu", "region": "us"}]],
    )
    pricing_strategy: str = Field(
        default="standard",
        description="Pricing strategy (standard, aggressive, premium)",
    )
    auto_approve: bool = Field(
        default=False,
        description="Skip manual approval",
    )


class PublishResponse(BaseModel):
    """Response from publishing."""

    success: bool
    candidate_product_id: UUID
    published_count: int
    failed_count: int
    listing_ids: list[UUID]
    failed_platforms: list[dict[str, Any]]


class PlatformListingResponse(BaseModel):
    """Platform listing response."""

    id: UUID
    candidate_product_id: UUID
    platform: str
    region: str
    platform_listing_id: str | None
    platform_url: str | None
    price: float
    currency: str
    inventory: int
    status: str
    total_sales: int
    total_revenue: float | None
    created_at: str
    last_synced_at: str | None
    sync_error: str | None = None
    sync_status: str | None = None
    platform_synced: bool | None = None

    class Config:
        from_attributes = True


class ListListingsResponse(BaseModel):
    """List of platform listings."""

    total: int
    listings: list[PlatformListingResponse]


class UpdateListingRequest(BaseModel):
    """Request to update a listing."""

    price: Decimal | None = Field(default=None, description="New price")
    inventory: int | None = Field(default=None, ge=0, description="New inventory")
    status: str | None = Field(default=None, description="New status")


class ListingActionResponse(BaseModel):
    """Response for listing actions with sync semantics."""

    success: bool
    listing_id: str
    status: str
    platform_synced: bool
    sync_status: str
    message: str


class SyncInventoryRequest(BaseModel):
    """Request to sync inventory."""

    platform_listing_ids: list[UUID] | None = Field(
        default=None,
        description="Specific listings to sync (None = all active)",
    )


class SyncInventoryResponse(BaseModel):
    """Response from inventory sync."""

    success: bool
    synced_count: int
    failed_count: int


# ============================================================================
# Helpers
# ============================================================================


def _serialize_listing(listing: PlatformListing) -> PlatformListingResponse:
    sync_status = "synced" if listing.last_synced_at else "local_only"
    platform_synced = listing.last_synced_at is not None and not listing.sync_error
    return PlatformListingResponse(
        id=listing.id,
        candidate_product_id=listing.candidate_product_id,
        platform=listing.platform.value,
        region=listing.region,
        platform_listing_id=listing.platform_listing_id,
        platform_url=listing.platform_url,
        price=float(listing.price),
        currency=listing.currency,
        inventory=listing.inventory,
        status=listing.status.value,
        total_sales=listing.total_sales,
        total_revenue=float(listing.total_revenue) if listing.total_revenue else None,
        created_at=listing.created_at.isoformat() if listing.created_at else "",
        last_synced_at=listing.last_synced_at.isoformat() if listing.last_synced_at else None,
        sync_error=listing.sync_error,
        sync_status=sync_status if not listing.sync_error else "sync_failed",
        platform_synced=platform_synced,
    )


def _mark_local_only_sync(listing: PlatformListing, message: str) -> None:
    listing.sync_error = message
    listing.last_synced_at = None


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/publish", response_model=PublishResponse)
async def publish_to_platforms(
    request: PublishRequest,
    db: AsyncSession = Depends(get_db),
):
    """Publish a product to target platforms."""
    logger.info(
        "api_publish_product",
        candidate_product_id=str(request.candidate_product_id),
        platforms=[p.platform for p in request.target_platforms],
    )

    candidate = await db.get(CandidateProduct, request.candidate_product_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate product not found")

    agent = PlatformPublisherAgent()
    context = AgentContext(
        strategy_run_id=candidate.strategy_run_id,
        db=db,
        input_data={
            "candidate_product_id": str(request.candidate_product_id),
            "target_platforms": [p.model_dump() for p in request.target_platforms],
            "pricing_strategy": request.pricing_strategy,
            "auto_approve": request.auto_approve,
        },
    )

    result = await agent.execute(context)
    if not result.success and result.output_data.get("published_count", 0) == 0:
        raise HTTPException(
            status_code=500,
            detail=result.error_message or "Publishing failed for all platforms",
        )

    return PublishResponse(
        success=result.success,
        candidate_product_id=request.candidate_product_id,
        published_count=result.output_data["published_count"],
        failed_count=result.output_data["failed_count"],
        listing_ids=[UUID(listing_id) for listing_id in result.output_data["listing_ids"]],
        failed_platforms=result.output_data.get("failed_platforms", []),
    )


@router.get("/products/{product_id}", response_model=ListListingsResponse)
async def list_product_listings(
    product_id: UUID,
    platform: str | None = Query(default=None, description="Filter by platform"),
    region: str | None = Query(default=None, description="Filter by region"),
    status: str | None = Query(default=None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
):
    """List all platform listings for a product."""
    logger.info(
        "api_list_listings",
        product_id=str(product_id),
        platform=platform,
        region=region,
    )

    query = select(PlatformListing).where(PlatformListing.candidate_product_id == product_id)

    if platform:
        query = query.where(PlatformListing.platform == TargetPlatform(platform))
    if region:
        query = query.where(PlatformListing.region == region)
    if status:
        query = query.where(PlatformListing.status == PlatformListingStatus(status))

    result = await db.execute(query.order_by(PlatformListing.created_at.desc()))
    listings = list(result.scalars().all())

    return ListListingsResponse(total=len(listings), listings=[_serialize_listing(listing) for listing in listings])


@router.get("/{listing_id}", response_model=PlatformListingResponse)
async def get_listing(
    listing_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single platform listing by ID."""
    listing = await db.get(PlatformListing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Platform listing not found")

    return _serialize_listing(listing)


@router.patch("/{listing_id}", response_model=ListingActionResponse)
async def update_listing(
    listing_id: UUID,
    request: UpdateListingRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update a platform listing in the local DB and expose sync semantics."""
    logger.info("api_update_listing", listing_id=str(listing_id))

    listing = await db.get(PlatformListing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Platform listing not found")

    if request.price is not None:
        listing.price = request.price
    if request.inventory is not None:
        listing.inventory = request.inventory
    if request.status is not None:
        listing.status = PlatformListingStatus(request.status)

    _mark_local_only_sync(listing, "Local DB updated only; platform API sync is not implemented yet.")
    await db.commit()
    await db.refresh(listing)

    return ListingActionResponse(
        success=True,
        listing_id=str(listing_id),
        status=listing.status.value,
        platform_synced=False,
        sync_status="local_only",
        message="Listing updated in local DB only. Platform sync is pending implementation.",
    )


@router.post("/sync-inventory", response_model=SyncInventoryResponse)
async def sync_inventory(
    request: SyncInventoryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Sync inventory to platforms."""
    logger.info(
        "api_sync_inventory",
        listing_count=len(request.platform_listing_ids) if request.platform_listing_ids else "all",
    )

    agent = PlatformSyncAgent()
    context = AgentContext(
        strategy_run_id=UUID("00000000-0000-0000-0000-000000000000"),
        db=db,
        input_data={
            "sync_type": "inventory",
            "platform_listing_ids": [str(lid) for lid in request.platform_listing_ids]
            if request.platform_listing_ids
            else None,
        },
    )

    result = await agent.execute(context)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error_message or "Inventory sync failed")

    return SyncInventoryResponse(
        success=result.success,
        synced_count=result.output_data.get("synced_count", 0),
        failed_count=result.output_data.get("failed_count", 0),
    )


@router.post("/{listing_id}/pause", response_model=ListingActionResponse)
async def pause_listing(
    listing_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Pause a platform listing locally and expose sync semantics."""
    logger.info("api_pause_listing", listing_id=str(listing_id))

    listing = await db.get(PlatformListing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Platform listing not found")

    listing.status = PlatformListingStatus.PAUSED
    _mark_local_only_sync(listing, "Listing paused locally; platform API sync is not implemented yet.")
    await db.commit()
    await db.refresh(listing)

    return ListingActionResponse(
        success=True,
        listing_id=str(listing_id),
        status=listing.status.value,
        platform_synced=False,
        sync_status="local_only",
        message="Listing paused in local DB only. Platform sync is pending implementation.",
    )


@router.post("/{listing_id}/resume", response_model=ListingActionResponse)
async def resume_listing(
    listing_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused listing locally and expose sync semantics."""
    logger.info("api_resume_listing", listing_id=str(listing_id))

    listing = await db.get(PlatformListing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Platform listing not found")

    listing.status = PlatformListingStatus.ACTIVE
    _mark_local_only_sync(listing, "Listing resumed locally; platform API sync is not implemented yet.")
    await db.commit()
    await db.refresh(listing)

    return ListingActionResponse(
        success=True,
        listing_id=str(listing_id),
        status=listing.status.value,
        platform_synced=False,
        sync_status="local_only",
        message="Listing resumed in local DB only. Platform sync is pending implementation.",
    )


@router.delete("/{listing_id}", response_model=ListingActionResponse)
async def delist_product(
    listing_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delist a product locally and expose sync semantics."""
    logger.info("api_delist_product", listing_id=str(listing_id))

    listing = await db.get(PlatformListing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Platform listing not found")

    listing.status = PlatformListingStatus.DELISTED
    _mark_local_only_sync(listing, "Listing delisted locally; platform API sync is not implemented yet.")
    await db.commit()
    await db.refresh(listing)

    return ListingActionResponse(
        success=True,
        listing_id=str(listing_id),
        status=listing.status.value,
        platform_synced=False,
        sync_status="local_only",
        message="Listing delisted in local DB only. Platform sync is pending implementation.",
    )


@router.get("/stats/distribution", response_model=dict[str, int])
async def get_listing_status_distribution(
    db: AsyncSession = Depends(get_db),
):
    """Get listing status distribution for analytics."""
    logger.info("api_get_listing_status_distribution")

    result = await db.execute(
        select(PlatformListing.status, func.count(PlatformListing.id)).group_by(PlatformListing.status)
    )
    rows = result.all()

    distribution = {status.value: 0 for status in PlatformListingStatus}
    for status, count in rows:
        distribution[status.value] = count
    return distribution


@router.get("/", response_model=ListListingsResponse)
async def list_all_listings(
    platform: str | None = Query(default=None, description="Filter by platform"),
    region: str | None = Query(default=None, description="Filter by region"),
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=500, description="Results per page"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
):
    """List all platform listings with pagination."""
    logger.info(
        "api_list_all_listings",
        platform=platform,
        region=region,
        status=status,
        limit=limit,
        offset=offset,
    )

    query = select(PlatformListing)

    if platform:
        query = query.where(PlatformListing.platform == TargetPlatform(platform))
    if region:
        query = query.where(PlatformListing.region == region)
    if status:
        query = query.where(PlatformListing.status == PlatformListingStatus(status))

    query = query.order_by(PlatformListing.created_at.desc())
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0

    result = await db.execute(query.limit(limit).offset(offset))
    listings = list(result.scalars().all())

    return ListListingsResponse(total=total, listings=[_serialize_listing(listing) for listing in listings])
