"""Content Asset Management API endpoints.

Provides REST API for:
- Generating content assets (images)
- Listing and filtering assets
- Approving/rejecting assets
- Managing asset metadata
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext
from app.agents.content_asset_manager import ContentAssetManagerAgent
from app.core.enums import AssetType
from app.core.logging import get_logger
from app.db.models import CandidateProduct, ContentAsset
from app.db.session import get_db

logger = get_logger(__name__)
router = APIRouter(prefix="/content-assets", tags=["content-assets"])


# ============================================================================
# Request/Response Models
# ============================================================================


class GenerateAssetsRequest(BaseModel):
    """Request to generate content assets."""

    candidate_product_id: UUID = Field(..., description="Candidate product ID")
    asset_types: list[str] = Field(
        default=["main_image"],
        description="Asset types to generate",
        examples=[["main_image", "detail_image"]],
    )
    styles: list[str] = Field(
        default=["minimalist"],
        description="Style presets",
        examples=[["minimalist", "luxury", "cute"]],
    )
    reference_images: list[str] | None = Field(
        default=None,
        description="Reference image URLs for IPAdapter",
    )
    generate_count: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Number of images per style",
    )
    platforms: list[str] = Field(
        default=[],
        description="Target platforms for tagging",
    )
    regions: list[str] = Field(
        default=[],
        description="Target regions for tagging",
    )


class GenerateAssetsResponse(BaseModel):
    """Response from asset generation."""

    success: bool
    candidate_product_id: UUID
    assets_created: int
    asset_ids: list[UUID]
    lifecycle_status: str | None


class ContentAssetResponse(BaseModel):
    """Content asset response."""

    id: UUID
    candidate_product_id: UUID
    asset_type: str
    style_tags: list[str]
    platform_tags: list[str]
    region_tags: list[str]
    file_url: str
    file_size: int | None
    dimensions: str | None
    format: str | None
    ai_quality_score: float | None
    human_approved: bool
    usage_count: int
    version: int
    created_at: str

    class Config:
        from_attributes = True


class ApproveAssetRequest(BaseModel):
    """Request to approve an asset."""

    notes: str | None = Field(default=None, description="Approval notes")


class ListAssetsResponse(BaseModel):
    """List of content assets."""

    total: int
    assets: list[ContentAssetResponse]


# ============================================================================
# Helpers
# ============================================================================


def _serialize_asset(asset: ContentAsset) -> ContentAssetResponse:
    return ContentAssetResponse(
        id=asset.id,
        candidate_product_id=asset.candidate_product_id,
        asset_type=asset.asset_type.value,
        style_tags=asset.style_tags or [],
        platform_tags=asset.platform_tags or [],
        region_tags=asset.region_tags or [],
        file_url=asset.file_url,
        file_size=asset.file_size,
        dimensions=asset.dimensions,
        format=asset.format,
        ai_quality_score=float(asset.ai_quality_score) if asset.ai_quality_score else None,
        human_approved=asset.human_approved,
        usage_count=asset.usage_count,
        version=asset.version,
        created_at=asset.created_at.isoformat() if asset.created_at else "",
    )


def _apply_asset_filters(
    query,
    *,
    candidate_product_id: UUID | None = None,
    asset_type: str | None = None,
    style: str | None = None,
    platform: str | None = None,
    region: str | None = None,
    approved: bool | None = None,
):
    if candidate_product_id:
        query = query.where(ContentAsset.candidate_product_id == candidate_product_id)
    if asset_type:
        query = query.where(ContentAsset.asset_type == AssetType(asset_type))
    if style:
        query = query.where(ContentAsset.style_tags.contains([style]))
    if platform:
        query = query.where(ContentAsset.platform_tags.contains([platform]))
    if region:
        query = query.where(ContentAsset.region_tags.contains([region]))
    if approved is not None:
        query = query.where(ContentAsset.human_approved.is_(approved))
    return query


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/generate", response_model=GenerateAssetsResponse)
async def generate_assets(
    request: GenerateAssetsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate content assets for a product."""
    logger.info(
        "api_generate_assets",
        candidate_product_id=str(request.candidate_product_id),
        asset_types=request.asset_types,
        styles=request.styles,
    )

    candidate = await db.get(CandidateProduct, request.candidate_product_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate product not found")

    agent = ContentAssetManagerAgent()
    context = AgentContext(
        strategy_run_id=candidate.strategy_run_id,
        db=db,
        input_data={
            "candidate_product_id": str(request.candidate_product_id),
            "asset_types": request.asset_types,
            "styles": request.styles,
            "reference_images": request.reference_images,
            "generate_count": request.generate_count,
            "platforms": request.platforms,
            "regions": request.regions,
        },
    )

    result = await agent.execute(context)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error_message or "Asset generation failed")

    return GenerateAssetsResponse(
        success=result.success,
        candidate_product_id=request.candidate_product_id,
        assets_created=result.output_data["assets_created"],
        asset_ids=[UUID(asset_id) for asset_id in result.output_data["asset_ids"]],
        lifecycle_status=result.output_data.get("lifecycle_status"),
    )


@router.get("/", response_model=ListAssetsResponse)
async def list_assets(
    candidate_product_id: UUID | None = Query(default=None, description="Filter by product ID"),
    asset_type: str | None = Query(default=None, description="Filter by asset type"),
    style: str | None = Query(default=None, description="Filter by style tag"),
    platform: str | None = Query(default=None, description="Filter by platform tag"),
    region: str | None = Query(default=None, description="Filter by region tag"),
    approved: bool | None = Query(default=None, description="Filter by approval status"),
    limit: int = Query(default=50, ge=1, le=500, description="Results per page"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
):
    """List content assets across products with filters and pagination."""
    logger.info(
        "api_list_all_assets",
        candidate_product_id=str(candidate_product_id) if candidate_product_id else None,
        asset_type=asset_type,
        style=style,
        platform=platform,
        region=region,
        approved=approved,
        limit=limit,
        offset=offset,
    )

    query = _apply_asset_filters(
        select(ContentAsset),
        candidate_product_id=candidate_product_id,
        asset_type=asset_type,
        style=style,
        platform=platform,
        region=region,
        approved=approved,
    ).order_by(ContentAsset.created_at.desc())

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0

    result = await db.execute(query.limit(limit).offset(offset))
    assets = list(result.scalars().all())

    return ListAssetsResponse(total=total, assets=[_serialize_asset(asset) for asset in assets])


@router.get("/products/{product_id}/best", response_model=ContentAssetResponse)
async def get_best_asset(
    product_id: UUID,
    asset_type: str = Query(default="main_image", description="Asset type"),
    platform: str | None = Query(default=None, description="Platform filter"),
    db: AsyncSession = Depends(get_db),
):
    """Get the best approved asset for a product."""
    logger.info(
        "api_get_best_asset",
        product_id=str(product_id),
        asset_type=asset_type,
        platform=platform,
    )

    query = _apply_asset_filters(
        select(ContentAsset),
        candidate_product_id=product_id,
        asset_type=asset_type,
        platform=platform,
        approved=True,
    ).order_by(
        ContentAsset.ai_quality_score.desc().nullslast(),
        ContentAsset.usage_count.desc(),
        ContentAsset.created_at.desc(),
    )

    result = await db.execute(query.limit(1))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="No suitable asset found")

    return _serialize_asset(asset)


@router.get("/products/{product_id}", response_model=ListAssetsResponse)
async def list_product_assets(
    product_id: UUID,
    asset_type: str | None = Query(default=None, description="Filter by asset type"),
    style: str | None = Query(default=None, description="Filter by style tag"),
    platform: str | None = Query(default=None, description="Filter by platform tag"),
    approved_only: bool = Query(default=False, description="Only show approved assets"),
    db: AsyncSession = Depends(get_db),
):
    """List all content assets for a product."""
    logger.info(
        "api_list_product_assets",
        product_id=str(product_id),
        asset_type=asset_type,
        style=style,
        platform=platform,
        approved_only=approved_only,
    )

    query = _apply_asset_filters(
        select(ContentAsset),
        candidate_product_id=product_id,
        asset_type=asset_type,
        style=style,
        platform=platform,
        approved=True if approved_only else None,
    ).order_by(ContentAsset.created_at.desc())

    result = await db.execute(query)
    assets = list(result.scalars().all())

    return ListAssetsResponse(total=len(assets), assets=[_serialize_asset(asset) for asset in assets])


@router.get("/{asset_id}", response_model=ContentAssetResponse)
async def get_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single content asset by ID."""
    asset = await db.get(ContentAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Content asset not found")

    return _serialize_asset(asset)


@router.post("/{asset_id}/approve")
async def approve_asset(
    asset_id: UUID,
    request: ApproveAssetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Approve a content asset for use."""
    logger.info("api_approve_asset", asset_id=str(asset_id))

    asset = await db.get(ContentAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Content asset not found")

    asset.human_approved = True
    asset.approval_notes = request.notes
    await db.commit()

    return {"success": True, "asset_id": str(asset_id), "approved": True}


@router.get("/stats/distribution", response_model=dict[str, int])
async def get_asset_type_distribution(
    db: AsyncSession = Depends(get_db),
):
    """Get asset type distribution for analytics."""
    logger.info("api_get_asset_type_distribution")

    result = await db.execute(
        select(ContentAsset.asset_type, func.count(ContentAsset.id)).group_by(ContentAsset.asset_type)
    )
    rows = result.all()

    distribution = {asset_type.value: 0 for asset_type in AssetType}
    for asset_type, count in rows:
        distribution[asset_type.value] = count
    return distribution


@router.post("/{asset_id}/reject")
async def reject_asset(
    asset_id: UUID,
    request: ApproveAssetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reject a content asset."""
    logger.info("api_reject_asset", asset_id=str(asset_id))

    asset = await db.get(ContentAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Content asset not found")

    asset.human_approved = False
    asset.approval_notes = request.notes
    await db.commit()

    return {"success": True, "asset_id": str(asset_id), "approved": False}


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a content asset.

    Note: This only deletes the database record. The file in MinIO is not deleted.
    """
    logger.info("api_delete_asset", asset_id=str(asset_id))

    asset = await db.get(ContentAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Content asset not found")

    await db.delete(asset)
    await db.commit()

    return {"success": True, "asset_id": str(asset_id), "deleted": True}
