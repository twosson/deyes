"""Listing metrics service for recording and querying daily performance data."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import ListingPerformanceDaily, PlatformListing


class ListingMetricsService:
    """Service for managing listing daily performance metrics."""

    def __init__(self):
        self.logger = get_logger(__name__)

    async def record_daily_metrics(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
        metric_date: date,
        impressions: int = 0,
        clicks: int = 0,
        orders: int = 0,
        units_sold: int = 0,
        revenue: Optional[Decimal] = None,
        ad_spend: Optional[Decimal] = None,
        returns_count: int = 0,
        refund_amount: Optional[Decimal] = None,
        raw_payload: Optional[dict] = None,
    ) -> ListingPerformanceDaily:
        """Record or update daily metrics for a listing.

        Performs upsert: if a record for (listing_id, metric_date) exists, updates it;
        otherwise creates a new record. Handles concurrent insert conflicts gracefully.
        """
        stmt = select(ListingPerformanceDaily).where(
            ListingPerformanceDaily.listing_id == listing_id,
            ListingPerformanceDaily.metric_date == metric_date,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.impressions = impressions
            existing.clicks = clicks
            existing.orders = orders
            existing.units_sold = units_sold
            existing.revenue = revenue
            existing.ad_spend = ad_spend
            existing.returns_count = returns_count
            existing.refund_amount = refund_amount
            existing.raw_payload = raw_payload
            await db.flush()
            self.logger.info(
                "listing_metrics_updated",
                listing_id=str(listing_id),
                metric_date=str(metric_date),
            )
            record = existing
        else:
            from uuid import uuid4

            try:
                async with db.begin_nested():
                    record = ListingPerformanceDaily(
                        id=uuid4(),
                        listing_id=listing_id,
                        metric_date=metric_date,
                        impressions=impressions,
                        clicks=clicks,
                        orders=orders,
                        units_sold=units_sold,
                        revenue=revenue,
                        ad_spend=ad_spend,
                        returns_count=returns_count,
                        refund_amount=refund_amount,
                        raw_payload=raw_payload,
                    )
                    db.add(record)
                    await db.flush()
                self.logger.info(
                    "listing_metrics_created",
                    listing_id=str(listing_id),
                    metric_date=str(metric_date),
                )
            except IntegrityError:
                self.logger.info(
                    "listing_metrics_insert_conflict_retrying",
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
                existing.ad_spend = ad_spend
                existing.returns_count = returns_count
                existing.refund_amount = refund_amount
                existing.raw_payload = raw_payload
                await db.flush()
                self.logger.info(
                    "listing_metrics_updated_after_conflict",
                    listing_id=str(listing_id),
                    metric_date=str(metric_date),
                )
                record = existing

        await self._refresh_listing_rollups(db, listing_id)
        return record

    async def get_metrics_history(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[ListingPerformanceDaily]:
        """Get daily metrics history for a listing."""
        stmt = select(ListingPerformanceDaily).where(ListingPerformanceDaily.listing_id == listing_id)

        if start_date:
            stmt = stmt.where(ListingPerformanceDaily.metric_date >= start_date)
        if end_date:
            stmt = stmt.where(ListingPerformanceDaily.metric_date <= end_date)

        stmt = stmt.order_by(ListingPerformanceDaily.metric_date.asc())

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_metrics_summary(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get aggregated metrics summary for a listing."""
        stmt = select(
            func.coalesce(func.sum(ListingPerformanceDaily.impressions), 0).label("total_impressions"),
            func.coalesce(func.sum(ListingPerformanceDaily.clicks), 0).label("total_clicks"),
            func.coalesce(func.sum(ListingPerformanceDaily.orders), 0).label("total_orders"),
            func.coalesce(func.sum(ListingPerformanceDaily.units_sold), 0).label("total_units_sold"),
            func.coalesce(func.sum(ListingPerformanceDaily.revenue), 0).label("total_revenue"),
            func.coalesce(func.sum(ListingPerformanceDaily.ad_spend), 0).label("total_ad_spend"),
            func.coalesce(func.sum(ListingPerformanceDaily.returns_count), 0).label("total_returns"),
            func.coalesce(func.sum(ListingPerformanceDaily.refund_amount), 0).label("total_refund_amount"),
        ).where(ListingPerformanceDaily.listing_id == listing_id)

        if start_date:
            stmt = stmt.where(ListingPerformanceDaily.metric_date >= start_date)
        if end_date:
            stmt = stmt.where(ListingPerformanceDaily.metric_date <= end_date)

        result = await db.execute(stmt)
        row = result.one()

        total_impressions = int(row.total_impressions) if row.total_impressions is not None else 0
        total_clicks = int(row.total_clicks) if row.total_clicks is not None else 0
        total_orders = int(row.total_orders) if row.total_orders is not None else 0
        total_units_sold = int(row.total_units_sold) if row.total_units_sold is not None else 0

        total_revenue = self._to_decimal(row.total_revenue)
        total_ad_spend = self._to_decimal(row.total_ad_spend)
        total_refund_amount = self._to_decimal(row.total_refund_amount)

        ctr = Decimal("0.0000")
        if total_impressions > 0:
            ctr = Decimal(total_clicks) / Decimal(total_impressions)

        order_rate = Decimal("0.0000")
        if total_clicks > 0:
            order_rate = Decimal(total_orders) / Decimal(total_clicks)

        return {
            "listing_id": str(listing_id),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_orders": total_orders,
            "total_units_sold": total_units_sold,
            "total_revenue": total_revenue,
            "total_ad_spend": total_ad_spend,
            "total_refund_amount": total_refund_amount,
            "ctr": ctr,
            "order_rate": order_rate,
        }

    async def _refresh_listing_rollups(self, db: AsyncSession, listing_id: UUID) -> None:
        """Refresh PlatformListing.total_sales and total_revenue from daily metrics."""
        stmt = select(
            func.coalesce(func.sum(ListingPerformanceDaily.units_sold), 0).label("total_sales"),
            func.coalesce(func.sum(ListingPerformanceDaily.revenue), 0).label("total_revenue"),
        ).where(ListingPerformanceDaily.listing_id == listing_id)

        result = await db.execute(stmt)
        row = result.one()

        listing = await db.get(PlatformListing, listing_id)
        if listing:
            listing.total_sales = int(row.total_sales) if row.total_sales is not None else 0
            listing.total_revenue = self._to_decimal(row.total_revenue)
            await db.flush()
            self.logger.info(
                "listing_rollups_refreshed",
                listing_id=str(listing_id),
                total_sales=listing.total_sales,
                total_revenue=str(listing.total_revenue),
            )

    def _to_decimal(self, value) -> Decimal:
        """Convert value to Decimal, returning Decimal("0.00") if None."""
        if value is None:
            return Decimal("0.00")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
