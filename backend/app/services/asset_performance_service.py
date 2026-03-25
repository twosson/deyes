"""Asset performance service for recording and querying daily asset performance data."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import AssetPerformanceDaily, ContentAsset


class AssetPerformanceService:
    """Service for managing asset daily performance metrics."""

    def __init__(self):
        self.logger = get_logger(__name__)

    async def record_daily_performance(
        self,
        db: AsyncSession,
        *,
        asset_id: UUID,
        listing_id: UUID,
        metric_date: date,
        impressions: int = 0,
        clicks: int = 0,
        orders: int = 0,
        units_sold: int = 0,
        revenue: Optional[Decimal] = None,
        usage_count: int = 0,
        raw_payload: Optional[dict] = None,
    ) -> AssetPerformanceDaily:
        """Record or update daily performance for an asset within a listing context."""
        stmt = select(AssetPerformanceDaily).where(
            AssetPerformanceDaily.asset_id == asset_id,
            AssetPerformanceDaily.listing_id == listing_id,
            AssetPerformanceDaily.metric_date == metric_date,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.impressions = impressions
            existing.clicks = clicks
            existing.orders = orders
            existing.units_sold = units_sold
            existing.revenue = revenue
            existing.usage_count = usage_count
            existing.raw_payload = raw_payload
            await db.flush()
            self.logger.info(
                "asset_performance_updated",
                asset_id=str(asset_id),
                listing_id=str(listing_id),
                metric_date=str(metric_date),
            )
            record = existing
        else:
            from uuid import uuid4

            try:
                async with db.begin_nested():
                    record = AssetPerformanceDaily(
                        id=uuid4(),
                        asset_id=asset_id,
                        listing_id=listing_id,
                        metric_date=metric_date,
                        impressions=impressions,
                        clicks=clicks,
                        orders=orders,
                        units_sold=units_sold,
                        revenue=revenue,
                        usage_count=usage_count,
                        raw_payload=raw_payload,
                    )
                    db.add(record)
                    await db.flush()
                self.logger.info(
                    "asset_performance_created",
                    asset_id=str(asset_id),
                    listing_id=str(listing_id),
                    metric_date=str(metric_date),
                )
            except IntegrityError:
                self.logger.info(
                    "asset_performance_insert_conflict_retrying",
                    asset_id=str(asset_id),
                    listing_id=str(listing_id),
                    metric_date=str(metric_date),
                )
                result = await db.execute(stmt)
                existing = result.scalar_one()
                existing.impressions = impressions
                existing.clicks = clicks
                existing.orders = orders
                existing.units_sold = units_sold
                existing.revenue = revenue
                existing.usage_count = usage_count
                existing.raw_payload = raw_payload
                await db.flush()
                self.logger.info(
                    "asset_performance_updated_after_conflict",
                    asset_id=str(asset_id),
                    listing_id=str(listing_id),
                    metric_date=str(metric_date),
                )
                record = existing

        await self._refresh_asset_rollups(db, asset_id)
        return record

    async def get_asset_history(
        self,
        db: AsyncSession,
        *,
        asset_id: UUID,
        listing_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[AssetPerformanceDaily]:
        """Get daily performance history for an asset, optionally scoped to one listing."""
        stmt = select(AssetPerformanceDaily).where(AssetPerformanceDaily.asset_id == asset_id)

        if listing_id:
            stmt = stmt.where(AssetPerformanceDaily.listing_id == listing_id)
        if start_date:
            stmt = stmt.where(AssetPerformanceDaily.metric_date >= start_date)
        if end_date:
            stmt = stmt.where(AssetPerformanceDaily.metric_date <= end_date)

        stmt = stmt.order_by(AssetPerformanceDaily.metric_date.asc(), AssetPerformanceDaily.listing_id.asc())

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_asset_summary(
        self,
        db: AsyncSession,
        *,
        asset_id: UUID,
        listing_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get aggregated performance summary for an asset."""
        stmt = select(
            func.coalesce(func.sum(AssetPerformanceDaily.impressions), 0).label("total_impressions"),
            func.coalesce(func.sum(AssetPerformanceDaily.clicks), 0).label("total_clicks"),
            func.coalesce(func.sum(AssetPerformanceDaily.orders), 0).label("total_orders"),
            func.coalesce(func.sum(AssetPerformanceDaily.units_sold), 0).label("total_units_sold"),
            func.coalesce(func.sum(AssetPerformanceDaily.revenue), 0).label("total_revenue"),
            func.coalesce(func.sum(AssetPerformanceDaily.usage_count), 0).label("total_usage_count"),
        ).where(AssetPerformanceDaily.asset_id == asset_id)

        if listing_id:
            stmt = stmt.where(AssetPerformanceDaily.listing_id == listing_id)
        if start_date:
            stmt = stmt.where(AssetPerformanceDaily.metric_date >= start_date)
        if end_date:
            stmt = stmt.where(AssetPerformanceDaily.metric_date <= end_date)

        result = await db.execute(stmt)
        row = result.one()

        total_impressions = int(row.total_impressions) if row.total_impressions is not None else 0
        total_clicks = int(row.total_clicks) if row.total_clicks is not None else 0
        total_orders = int(row.total_orders) if row.total_orders is not None else 0
        total_units_sold = int(row.total_units_sold) if row.total_units_sold is not None else 0
        total_usage_count = int(row.total_usage_count) if row.total_usage_count is not None else 0

        total_revenue = self._to_decimal(row.total_revenue)

        ctr = Decimal("0.0000")
        if total_impressions > 0:
            ctr = Decimal(total_clicks) / Decimal(total_impressions)

        return {
            "asset_id": str(asset_id),
            "listing_id": str(listing_id) if listing_id else None,
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_orders": total_orders,
            "total_units_sold": total_units_sold,
            "total_revenue": total_revenue,
            "total_usage_count": total_usage_count,
            "ctr": ctr,
        }

    async def _refresh_asset_rollups(self, db: AsyncSession, asset_id: UUID) -> None:
        """Refresh ContentAsset.usage_count from daily performance data."""
        stmt = select(
            func.coalesce(func.sum(AssetPerformanceDaily.usage_count), 0).label("usage_count"),
        ).where(AssetPerformanceDaily.asset_id == asset_id)

        result = await db.execute(stmt)
        row = result.one()

        asset = await db.get(ContentAsset, asset_id)
        if asset:
            asset.usage_count = int(row.usage_count) if row.usage_count is not None else 0
            await db.flush()
            self.logger.info(
                "asset_rollups_refreshed",
                asset_id=str(asset_id),
                usage_count=asset.usage_count,
            )

    def _to_decimal(self, value) -> Decimal:
        """Convert value to Decimal, returning Decimal("0.00") if None."""
        if value is None:
            return Decimal("0.00")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
