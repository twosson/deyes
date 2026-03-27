"""Performance metrics calculation service."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AssetPerformanceDaily, ListingPerformanceDaily


class PerformanceCalculator:
    """Service for calculating performance metrics."""

    @staticmethod
    def calculate_ctr(impressions: int, clicks: int) -> float:
        """Calculate CTR (Click-Through Rate)."""
        return clicks / impressions if impressions > 0 else 0.0

    @staticmethod
    def calculate_cvr(clicks: int, orders: int) -> float:
        """Calculate CVR (Conversion Rate)."""
        return orders / clicks if clicks > 0 else 0.0

    @staticmethod
    def calculate_roi(revenue: Decimal, ad_spend: Decimal) -> Decimal:
        """Calculate ROI (Return on Investment)."""
        if ad_spend == 0:
            return Decimal("0")
        return (revenue - ad_spend) / ad_spend

    @staticmethod
    def calculate_roas(revenue: Decimal, ad_spend: Decimal) -> Decimal:
        """Calculate ROAS (Return on Ad Spend)."""
        return revenue / ad_spend if ad_spend > 0 else Decimal("0")

    @staticmethod
    async def get_listing_7day_metrics(
        db: AsyncSession,
        listing_id: UUID,
        lookback_days: int = 7,
    ) -> Optional[dict]:
        """Get listing aggregated metrics for the last N days.

        Args:
            db: Database session
            listing_id: Listing ID
            lookback_days: Number of days to look back (default 7)

        Returns:
            Dict with aggregated metrics or None if no data
        """
        lookback_date = date.today() - timedelta(days=lookback_days)

        stmt = select(ListingPerformanceDaily).where(
            ListingPerformanceDaily.listing_id == listing_id,
            ListingPerformanceDaily.metric_date >= lookback_date,
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        if not records:
            return None

        # Aggregate calculations
        total_impressions = sum(r.impressions for r in records)
        total_clicks = sum(r.clicks for r in records)
        total_orders = sum(r.orders for r in records)
        total_revenue = sum(r.revenue or Decimal("0") for r in records)
        total_ad_spend = sum(r.ad_spend or Decimal("0") for r in records)

        return {
            "ctr": PerformanceCalculator.calculate_ctr(total_impressions, total_clicks),
            "cvr": PerformanceCalculator.calculate_cvr(total_clicks, total_orders),
            "roi": PerformanceCalculator.calculate_roi(total_revenue, total_ad_spend),
            "roas": PerformanceCalculator.calculate_roas(total_revenue, total_ad_spend),
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "data_points": len(records),
        }

    @staticmethod
    async def get_asset_7day_metrics(
        db: AsyncSession,
        asset_id: UUID,
        listing_id: Optional[UUID] = None,
        lookback_days: int = 7,
    ) -> Optional[dict]:
        """Get asset aggregated metrics for the last N days.

        Args:
            db: Database session
            asset_id: Asset ID
            listing_id: Optional listing ID filter
            lookback_days: Number of days to look back (default 7)

        Returns:
            Dict with aggregated metrics or None if no data
        """
        lookback_date = date.today() - timedelta(days=lookback_days)

        stmt = select(AssetPerformanceDaily).where(
            AssetPerformanceDaily.asset_id == asset_id,
            AssetPerformanceDaily.metric_date >= lookback_date,
        )

        if listing_id:
            stmt = stmt.where(AssetPerformanceDaily.listing_id == listing_id)

        result = await db.execute(stmt)
        records = result.scalars().all()

        if not records:
            return None

        # Aggregate calculations
        total_impressions = sum(r.impressions for r in records)
        total_clicks = sum(r.clicks for r in records)
        total_orders = sum(r.orders for r in records)
        total_revenue = sum(r.revenue or Decimal("0") for r in records)

        return {
            "ctr": PerformanceCalculator.calculate_ctr(total_impressions, total_clicks),
            "cvr": PerformanceCalculator.calculate_cvr(total_clicks, total_orders),
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "data_points": len(records),
        }
