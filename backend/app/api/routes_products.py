"""Master Product Management API endpoints.

Provides REST API for:
- Listing products with lifecycle status
- Updating product lifecycle
- Getting product overview (assets + listings)
- Product statistics
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CandidateStatus, ProductLifecycle
from app.core.logging import get_logger
from app.db.models import CandidateProduct, ContentAsset, PlatformListing, PricingAssessment, SupplierMatch
from app.db.session import get_db

logger = get_logger(__name__)
router = APIRouter(prefix="/products", tags=["products"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ProductResponse(BaseModel):
    """Product response."""

    id: UUID
    internal_sku: str | None
    title: str
    category: str | None
    source_platform: str
    source_product_id: str | None
    platform_price: float | None
    lifecycle_status: str | None
    status: str
    created_at: str
    updated_at: str | None

    assets_count: int = 0
    listings_count: int = 0

    class Config:
        from_attributes = True


class ProductDetailResponse(BaseModel):
    """Detailed product response with assets and listings."""

    id: UUID
    internal_sku: str | None
    title: str
    category: str | None
    source_platform: str
    source_product_id: str | None
    source_url: str | None
    platform_price: float | None
    sales_count: int | None
    rating: float | None
    main_image_url: str | None
    normalized_attributes: dict | None
    lifecycle_status: str | None
    status: str
    created_at: str
    updated_at: str | None
    assets: list[dict]
    listings: list[dict]
    supplier_matches: list[dict]
    pricing_assessment: dict | None = None

    class Config:
        from_attributes = True


class ListProductsResponse(BaseModel):
    """List of products."""

    total: int
    products: list[ProductResponse]


class UpdateLifecycleRequest(BaseModel):
    """Request to update product lifecycle."""

    lifecycle_status: str = Field(..., description="New lifecycle status")


class ProductStatsResponse(BaseModel):
    """Product statistics."""

    total_products: int
    by_lifecycle: dict[str, int]
    by_status: dict[str, int]
    total_assets: int
    total_listings: int
    total_published: int


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/stats/overview", response_model=ProductStatsResponse)
async def get_product_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get product statistics overview."""
    logger.info("api_get_product_stats")

    total_products_result = await db.execute(select(func.count()).select_from(CandidateProduct))
    total_assets_result = await db.execute(select(func.count()).select_from(ContentAsset))
    total_listings_result = await db.execute(select(func.count()).select_from(PlatformListing))
    total_published_result = await db.execute(
        select(func.count()).where(CandidateProduct.lifecycle_status == ProductLifecycle.PUBLISHED)
    )

    lifecycle_counts_result = await db.execute(
        select(CandidateProduct.lifecycle_status, func.count(CandidateProduct.id)).group_by(
            CandidateProduct.lifecycle_status
        )
    )
    status_counts_result = await db.execute(
        select(CandidateProduct.status, func.count(CandidateProduct.id)).group_by(
            CandidateProduct.status
        )
    )

    by_lifecycle = {lifecycle.value: 0 for lifecycle in ProductLifecycle}
    for lifecycle, count in lifecycle_counts_result.all():
        if lifecycle is not None:
            by_lifecycle[lifecycle.value] = count

    by_status = {status.value: 0 for status in CandidateStatus}
    for status, count in status_counts_result.all():
        by_status[status.value] = count

    return ProductStatsResponse(
        total_products=total_products_result.scalar() or 0,
        by_lifecycle=by_lifecycle,
        by_status=by_status,
        total_assets=total_assets_result.scalar() or 0,
        total_listings=total_listings_result.scalar() or 0,
        total_published=total_published_result.scalar() or 0,
    )


@router.get("/", response_model=ListProductsResponse)
async def list_products(
    lifecycle_status: str | None = Query(default=None, description="Filter by lifecycle status"),
    status: str | None = Query(default=None, description="Filter by candidate status"),
    category: str | None = Query(default=None, description="Filter by category"),
    search: str | None = Query(default=None, description="Search in title"),
    limit: int = Query(default=50, ge=1, le=500, description="Results per page"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
):
    """List all products with pagination and filters."""
    logger.info(
        "api_list_products",
        lifecycle_status=lifecycle_status,
        status=status,
        category=category,
        search=search,
        limit=limit,
        offset=offset,
    )

    query = select(CandidateProduct)

    if lifecycle_status:
        query = query.where(CandidateProduct.lifecycle_status == ProductLifecycle(lifecycle_status))
    if status:
        query = query.where(CandidateProduct.status == CandidateStatus(status))
    if category:
        query = query.where(CandidateProduct.category == category)
    if search:
        query = query.where(CandidateProduct.title.ilike(f"%{search}%"))

    query = query.order_by(CandidateProduct.created_at.desc())

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0

    result = await db.execute(query.limit(limit).offset(offset))
    products = list(result.scalars().all())

    product_ids = [product.id for product in products]
    assets_counts: dict[UUID, int] = {}
    listings_counts: dict[UUID, int] = {}

    if product_ids:
        assets_count_result = await db.execute(
            select(ContentAsset.candidate_product_id, func.count(ContentAsset.id))
            .where(ContentAsset.candidate_product_id.in_(product_ids))
            .group_by(ContentAsset.candidate_product_id)
        )
        assets_counts = dict(assets_count_result.all())

        listings_count_result = await db.execute(
            select(PlatformListing.candidate_product_id, func.count(PlatformListing.id))
            .where(PlatformListing.candidate_product_id.in_(product_ids))
            .group_by(PlatformListing.candidate_product_id)
        )
        listings_counts = dict(listings_count_result.all())

    return ListProductsResponse(
        total=total,
        products=[
            ProductResponse(
                id=product.id,
                internal_sku=product.internal_sku,
                title=product.title,
                category=product.category,
                source_platform=product.source_platform.value,
                source_product_id=product.source_product_id,
                platform_price=float(product.platform_price) if product.platform_price else None,
                lifecycle_status=product.lifecycle_status.value if product.lifecycle_status else None,
                status=product.status.value,
                created_at=product.created_at.isoformat() if product.created_at else "",
                updated_at=product.updated_at.isoformat() if product.updated_at else None,
                assets_count=assets_counts.get(product.id, 0),
                listings_count=listings_counts.get(product.id, 0),
            )
            for product in products
        ],
    )


@router.get("/{product_id}", response_model=ProductDetailResponse)
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed product information including assets and listings."""
    logger.info("api_get_product", product_id=str(product_id))

    product = await db.get(CandidateProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    assets_result = await db.execute(
        select(ContentAsset)
        .where(ContentAsset.candidate_product_id == product_id)
        .order_by(ContentAsset.created_at.desc())
    )
    listings_result = await db.execute(
        select(PlatformListing)
        .where(PlatformListing.candidate_product_id == product_id)
        .order_by(PlatformListing.created_at.desc())
    )
    suppliers_result = await db.execute(
        select(SupplierMatch)
        .where(SupplierMatch.candidate_product_id == product_id)
        .order_by(SupplierMatch.created_at.desc())
    )
    pricing_result = await db.execute(
        select(PricingAssessment).where(PricingAssessment.candidate_product_id == product_id)
    )

    assets = list(assets_result.scalars().all())
    listings = list(listings_result.scalars().all())
    suppliers = list(suppliers_result.scalars().all())
    pricing = pricing_result.scalar_one_or_none()

    return ProductDetailResponse(
        id=product.id,
        internal_sku=product.internal_sku,
        title=product.title,
        category=product.category,
        source_platform=product.source_platform.value,
        source_product_id=product.source_product_id,
        source_url=product.source_url,
        platform_price=float(product.platform_price) if product.platform_price else None,
        sales_count=product.sales_count,
        rating=float(product.rating) if product.rating else None,
        main_image_url=product.main_image_url,
        normalized_attributes=product.normalized_attributes,
        lifecycle_status=product.lifecycle_status.value if product.lifecycle_status else None,
        status=product.status.value,
        created_at=product.created_at.isoformat() if product.created_at else "",
        updated_at=product.updated_at.isoformat() if product.updated_at else None,
        assets=[
            {
                "id": str(asset.id),
                "asset_type": asset.asset_type.value,
                "file_url": asset.file_url,
                "style_tags": asset.style_tags or [],
                "human_approved": asset.human_approved,
                "ai_quality_score": float(asset.ai_quality_score) if asset.ai_quality_score else None,
            }
            for asset in assets
        ],
        listings=[
            {
                "id": str(listing.id),
                "platform": listing.platform.value,
                "region": listing.region,
                "platform_listing_id": listing.platform_listing_id,
                "price": float(listing.price),
                "currency": listing.currency,
                "inventory": listing.inventory,
                "status": listing.status.value,
                "sync_error": listing.sync_error,
            }
            for listing in listings
        ],
        supplier_matches=[
            {
                "id": str(supplier.id),
                "supplier_name": supplier.supplier_name,
                "supplier_url": supplier.supplier_url,
                "supplier_sku": supplier.supplier_sku,
                "supplier_price": float(supplier.supplier_price) if supplier.supplier_price else None,
                "moq": supplier.moq,
                "selected": supplier.selected,
                "confidence_score": float(supplier.confidence_score) if supplier.confidence_score else None,
            }
            for supplier in suppliers
        ],
        pricing_assessment={
            "estimated_shipping_cost": float(pricing.estimated_shipping_cost) if pricing and pricing.estimated_shipping_cost is not None else None,
            "platform_commission_rate": float(pricing.platform_commission_rate) if pricing and pricing.platform_commission_rate is not None else None,
            "payment_fee_rate": float(pricing.payment_fee_rate) if pricing and pricing.payment_fee_rate is not None else None,
            "return_rate_assumption": float(pricing.return_rate_assumption) if pricing and pricing.return_rate_assumption is not None else None,
            "total_cost": float(pricing.total_cost) if pricing and pricing.total_cost is not None else None,
            "estimated_margin": float(pricing.estimated_margin) if pricing and pricing.estimated_margin is not None else None,
            "margin_percentage": float(pricing.margin_percentage) if pricing and pricing.margin_percentage is not None else None,
            "recommended_price": float(pricing.recommended_price) if pricing and pricing.recommended_price is not None else None,
            "profitability_decision": pricing.profitability_decision.value if pricing and pricing.profitability_decision else None,
            "explanation": pricing.explanation if pricing else None,
        } if pricing else None,
    )


@router.patch("/{product_id}/lifecycle")
async def update_lifecycle(
    product_id: UUID,
    request: UpdateLifecycleRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update product lifecycle status."""
    logger.info(
        "api_update_lifecycle",
        product_id=str(product_id),
        new_status=request.lifecycle_status,
    )

    product = await db.get(CandidateProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.lifecycle_status = ProductLifecycle(request.lifecycle_status)
    await db.commit()
    await db.refresh(product)

    return {
        "success": True,
        "product_id": str(product_id),
        "lifecycle_status": product.lifecycle_status.value if product.lifecycle_status else None,
    }


@router.delete("/{product_id}")
async def delete_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a product and all related data.

    Warning: This will cascade delete:
    - Content assets
    - Platform listings
    - Supplier matches
    - Pricing/risk assessments
    """
    logger.info("api_delete_product", product_id=str(product_id))

    product = await db.get(CandidateProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.delete(product)
    await db.commit()

    return {"success": True, "product_id": str(product_id), "deleted": True}
