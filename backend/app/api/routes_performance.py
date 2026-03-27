"""Performance API routes for asset and listing metrics."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AssetPerformanceDaily,
    ContentAsset,
    ListingPerformanceDaily,
    PlatformListing,
    RunEvent,
)
from app.db.session import get_db

router = APIRouter()


def _decimal_to_float(value) -> float | None:
    """Convert Decimal to float for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


@router.get("/performance/assets/{asset_id}")
async def get_asset_performance(
    asset_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    listing_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get daily performance metrics for an asset."""
    stmt = select(AssetPerformanceDaily).where(AssetPerformanceDaily.asset_id == asset_id)

    if start_date:
        stmt = stmt.where(AssetPerformanceDaily.metric_date >= start_date)
    if end_date:
        stmt = stmt.where(AssetPerformanceDaily.metric_date <= end_date)
    if listing_id:
        stmt = stmt.where(AssetPerformanceDaily.listing_id == listing_id)

    stmt = stmt.order_by(AssetPerformanceDaily.metric_date.asc())
    result = await db.execute(stmt)
    records = result.scalars().all()

    return [
        {
            "id": str(record.id),
            "asset_id": str(record.asset_id),
            "listing_id": str(record.listing_id),
            "metric_date": record.metric_date.isoformat(),
            "impressions": record.impressions,
            "clicks": record.clicks,
            "orders": record.orders,
            "units_sold": record.units_sold,
            "revenue": _decimal_to_float(record.revenue),
            "ad_spend": _decimal_to_float(record.ad_spend),
            "returns_count": record.returns_count,
            "refund_amount": _decimal_to_float(record.refund_amount),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
        for record in records
    ]


@router.get("/performance/listings/{listing_id}")
async def get_listing_performance(
    listing_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get daily performance metrics for a listing."""
    stmt = select(ListingPerformanceDaily).where(ListingPerformanceDaily.listing_id == listing_id)

    if start_date:
        stmt = stmt.where(ListingPerformanceDaily.metric_date >= start_date)
    if end_date:
        stmt = stmt.where(ListingPerformanceDaily.metric_date <= end_date)

    stmt = stmt.order_by(ListingPerformanceDaily.metric_date.asc())
    result = await db.execute(stmt)
    records = result.scalars().all()

    return [
        {
            "id": str(record.id),
            "listing_id": str(record.listing_id),
            "metric_date": record.metric_date.isoformat(),
            "impressions": record.impressions,
            "clicks": record.clicks,
            "orders": record.orders,
            "units_sold": record.units_sold,
            "revenue": _decimal_to_float(record.revenue),
            "ad_spend": _decimal_to_float(record.ad_spend),
            "returns_count": record.returns_count,
            "refund_amount": _decimal_to_float(record.refund_amount),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
        for record in records
    ]


@router.get("/performance/trends")
async def get_performance_trends(
    asset_ids: list[UUID] | None = None,
    listing_ids: list[UUID] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    granularity: str = "daily",
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated performance trends over time."""
    if granularity != "daily":
        raise HTTPException(status_code=400, detail="Only 'daily' granularity is currently supported")

    # Base query aggregates by date
    stmt = select(
        AssetPerformanceDaily.metric_date.label("date"),
        func.sum(AssetPerformanceDaily.impressions).label("impressions"),
        func.sum(AssetPerformanceDaily.clicks).label("clicks"),
        func.sum(AssetPerformanceDaily.orders).label("orders"),
        func.sum(AssetPerformanceDaily.revenue).label("revenue"),
    )

    conditions = []
    if asset_ids:
        conditions.append(AssetPerformanceDaily.asset_id.in_(asset_ids))
    if listing_ids:
        conditions.append(AssetPerformanceDaily.listing_id.in_(listing_ids))
    if start_date:
        conditions.append(AssetPerformanceDaily.metric_date >= start_date)
    if end_date:
        conditions.append(AssetPerformanceDaily.metric_date <= end_date)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.group_by(AssetPerformanceDaily.metric_date).order_by(AssetPerformanceDaily.metric_date.asc())

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "date": row.date.isoformat(),
            "impressions": int(row.impressions or 0),
            "clicks": int(row.clicks or 0),
            "orders": int(row.orders or 0),
            "revenue": _decimal_to_float(row.revenue) or 0.0,
        }
        for row in rows
    ]


@router.get("/performance/assets/{asset_id}/summary")
async def get_asset_performance_summary(
    asset_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated performance summary for an asset."""
    stmt = select(
        func.coalesce(func.sum(AssetPerformanceDaily.impressions), 0).label("impressions"),
        func.coalesce(func.sum(AssetPerformanceDaily.clicks), 0).label("clicks"),
        func.coalesce(func.sum(AssetPerformanceDaily.orders), 0).label("orders"),
        func.coalesce(func.sum(AssetPerformanceDaily.units_sold), 0).label("units_sold"),
        func.coalesce(func.sum(AssetPerformanceDaily.revenue), 0).label("revenue"),
        func.coalesce(func.sum(AssetPerformanceDaily.ad_spend), 0).label("ad_spend"),
        func.coalesce(func.sum(AssetPerformanceDaily.returns_count), 0).label("returns_count"),
        func.coalesce(func.sum(AssetPerformanceDaily.refund_amount), 0).label("refund_amount"),
    ).where(AssetPerformanceDaily.asset_id == asset_id)

    if start_date:
        stmt = stmt.where(AssetPerformanceDaily.metric_date >= start_date)
    if end_date:
        stmt = stmt.where(AssetPerformanceDaily.metric_date <= end_date)

    result = await db.execute(stmt)
    row = result.one()

    impressions = int(row.impressions or 0)
    clicks = int(row.clicks or 0)
    orders = int(row.orders or 0)
    revenue = _decimal_to_float(row.revenue) or 0.0
    ad_spend = _decimal_to_float(row.ad_spend) or 0.0

    ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
    cvr = (orders / clicks * 100) if clicks > 0 else 0.0
    roas = (revenue / ad_spend) if ad_spend > 0 else 0.0
    avg_order_value = (revenue / orders) if orders > 0 else 0.0

    return {
        "impressions": impressions,
        "clicks": clicks,
        "orders": orders,
        "units_sold": int(row.units_sold or 0),
        "revenue": revenue,
        "ad_spend": ad_spend,
        "returns_count": int(row.returns_count or 0),
        "refund_amount": _decimal_to_float(row.refund_amount) or 0.0,
        "ctr": ctr,
        "cvr": cvr,
        "roas": roas,
        "avg_order_value": avg_order_value,
    }


# ============================================================================
# Dashboard Endpoints
# ============================================================================


@router.get("/performance/dashboard/overview")
async def get_performance_overview(
    db: AsyncSession = Depends(get_db),
):
    """Get performance overview for dashboard."""
    # Count active listings with performance data
    seven_days_ago = date.today() - timedelta(days=7)

    active_listings_stmt = select(func.count(func.distinct(PlatformListing.id))).where(
        PlatformListing.status.in_(["active", "paused"])
    )
    active_listings_result = await db.execute(active_listings_stmt)
    active_listings_count = active_listings_result.scalar() or 0

    # Count listings with recent performance data
    tracked_listings_stmt = select(func.count(func.distinct(ListingPerformanceDaily.listing_id))).where(
        ListingPerformanceDaily.metric_date >= seven_days_ago
    )
    tracked_listings_result = await db.execute(tracked_listings_stmt)
    tracked_listings_count = tracked_listings_result.scalar() or 0

    # Count low ROI listings (ROI < 10%)
    low_roi_stmt = select(
        ListingPerformanceDaily.listing_id,
        func.sum(ListingPerformanceDaily.revenue).label("total_revenue"),
        func.sum(ListingPerformanceDaily.ad_spend).label("total_ad_spend"),
    ).where(
        ListingPerformanceDaily.metric_date >= seven_days_ago
    ).group_by(ListingPerformanceDaily.listing_id)

    low_roi_result = await db.execute(low_roi_stmt)
    low_roi_count = 0
    for row in low_roi_result:
        revenue = float(row.total_revenue or 0)
        ad_spend = float(row.total_ad_spend or 0)
        if ad_spend > 0:
            roi = (revenue - ad_spend) / ad_spend
            if roi < 0.1:
                low_roi_count += 1

    # Count low CTR assets (CTR < 1%)
    low_ctr_stmt = select(
        AssetPerformanceDaily.asset_id,
        func.sum(AssetPerformanceDaily.impressions).label("total_impressions"),
        func.sum(AssetPerformanceDaily.clicks).label("total_clicks"),
    ).where(
        AssetPerformanceDaily.metric_date >= seven_days_ago
    ).group_by(AssetPerformanceDaily.asset_id)

    low_ctr_result = await db.execute(low_ctr_stmt)
    low_ctr_count = 0
    for row in low_ctr_result:
        impressions = int(row.total_impressions or 0)
        clicks = int(row.total_clicks or 0)
        if impressions >= 100:
            ctr = (clicks / impressions) * 100
            if ctr < 1.0:
                low_ctr_count += 1

    return {
        "active_listings_count": active_listings_count,
        "tracked_listings_count": tracked_listings_count,
        "low_roi_alerts": low_roi_count,
        "low_ctr_alerts": low_ctr_count,
    }


@router.get("/performance/dashboard/listings")
async def get_dashboard_listings(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get listing performance summaries for dashboard."""
    seven_days_ago = date.today() - timedelta(days=7)

    # Get listings with recent performance data
    stmt = (
        select(
            PlatformListing.id,
            PlatformListing.platform,
            PlatformListing.region,
            PlatformListing.platform_listing_id,
            PlatformListing.price,
            PlatformListing.currency,
            PlatformListing.status,
            func.sum(ListingPerformanceDaily.impressions).label("impressions"),
            func.sum(ListingPerformanceDaily.clicks).label("clicks"),
            func.sum(ListingPerformanceDaily.orders).label("orders"),
            func.sum(ListingPerformanceDaily.revenue).label("revenue"),
            func.sum(ListingPerformanceDaily.ad_spend).label("ad_spend"),
        )
        .join(ListingPerformanceDaily, PlatformListing.id == ListingPerformanceDaily.listing_id)
        .where(ListingPerformanceDaily.metric_date >= seven_days_ago)
        .group_by(
            PlatformListing.id,
            PlatformListing.platform,
            PlatformListing.region,
            PlatformListing.platform_listing_id,
            PlatformListing.price,
            PlatformListing.currency,
            PlatformListing.status,
        )
        .order_by(desc(func.sum(ListingPerformanceDaily.revenue)))
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    listings = []
    for row in rows:
        impressions = int(row.impressions or 0)
        clicks = int(row.clicks or 0)
        orders = int(row.orders or 0)
        revenue = float(row.revenue or 0)
        ad_spend = float(row.ad_spend or 0)

        ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
        cvr = (orders / clicks * 100) if clicks > 0 else 0.0
        roi = ((revenue - ad_spend) / ad_spend * 100) if ad_spend > 0 else 0.0
        roas = (revenue / ad_spend) if ad_spend > 0 else 0.0

        listings.append({
            "listing_id": str(row.id),
            "platform": row.platform.value if hasattr(row.platform, "value") else row.platform,
            "region": row.region,
            "platform_listing_id": row.platform_listing_id,
            "price": float(row.price),
            "currency": row.currency,
            "status": row.status.value if hasattr(row.status, "value") else row.status,
            "impressions": impressions,
            "clicks": clicks,
            "orders": orders,
            "revenue": revenue,
            "ad_spend": ad_spend,
            "ctr": ctr,
            "cvr": cvr,
            "roi": roi,
            "roas": roas,
        })

    return {"items": listings, "count": len(listings)}


@router.get("/performance/dashboard/assets")
async def get_dashboard_assets(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get asset performance summaries for dashboard, ranked by CTR."""
    seven_days_ago = date.today() - timedelta(days=7)

    # Get assets with recent performance data
    stmt = (
        select(
            ContentAsset.id,
            ContentAsset.asset_type,
            ContentAsset.file_url,
            ContentAsset.ai_quality_score,
            func.sum(AssetPerformanceDaily.impressions).label("impressions"),
            func.sum(AssetPerformanceDaily.clicks).label("clicks"),
            func.sum(AssetPerformanceDaily.orders).label("orders"),
            func.sum(AssetPerformanceDaily.revenue).label("revenue"),
        )
        .join(AssetPerformanceDaily, ContentAsset.id == AssetPerformanceDaily.asset_id)
        .where(AssetPerformanceDaily.metric_date >= seven_days_ago)
        .group_by(
            ContentAsset.id,
            ContentAsset.asset_type,
            ContentAsset.file_url,
            ContentAsset.ai_quality_score,
        )
        .order_by(desc(func.sum(AssetPerformanceDaily.clicks) / func.nullif(func.sum(AssetPerformanceDaily.impressions), 0)))
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    assets = []
    for row in rows:
        impressions = int(row.impressions or 0)
        clicks = int(row.clicks or 0)
        orders = int(row.orders or 0)
        revenue = float(row.revenue or 0)

        ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
        cvr = (orders / clicks * 100) if clicks > 0 else 0.0

        assets.append({
            "asset_id": str(row.id),
            "asset_type": row.asset_type.value if hasattr(row.asset_type, "value") else row.asset_type,
            "file_url": row.file_url,
            "ai_quality_score": float(row.ai_quality_score) if row.ai_quality_score else None,
            "impressions": impressions,
            "clicks": clicks,
            "orders": orders,
            "revenue": revenue,
            "ctr": ctr,
            "cvr": cvr,
        })

    return {"items": assets, "count": len(assets)}


@router.get("/performance/dashboard/recent-actions")
async def get_recent_auto_actions(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get recent auto action events for dashboard."""
    stmt = (
        select(RunEvent)
        .where(
            RunEvent.event_type.in_([
                "auto_reprice",
                "auto_pause",
                "auto_asset_switch",
                "auto_reprice_failed",
                "auto_pause_failed",
                "auto_asset_switch_failed",
            ])
        )
        .order_by(desc(RunEvent.created_at))
        .limit(limit)
    )

    result = await db.execute(stmt)
    events = result.scalars().all()

    actions = []
    for event in events:
        payload = event.event_payload or {}
        actions.append({
            "event_id": str(event.id),
            "event_type": event.event_type,
            "listing_id": payload.get("listing_id"),
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "payload": payload,
        })

    return {"items": actions, "count": len(actions)}
