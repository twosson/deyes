"""生命周期信号聚合服务。

为生命周期引擎准备统一输入信号。
"""
from decimal import Decimal
from typing import Optional
from uuid import UUID
from datetime import date, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import (
    InventoryLevel,
    ListingPerformanceDaily,
    ProfitLedger,
    PlatformListing,
)

logger = get_logger(__name__)


class LifecycleSignalService:
    """生命周期信号聚合服务。

    聚合 sales trend, refund trend, profit margin trend, inventory coverage days,
    supplier risk signal, content performance signal。
    """

    def __init__(self):
        """初始化信号服务。"""
        pass

    async def get_signal_snapshot(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        lookback_days: int = 30,
    ) -> dict:
        """获取 SKU 的生命周期信号快照。

        Args:
            db: 数据库会话
            product_variant_id: SKU ID
            lookback_days: 回溯天数

        Returns:
            {
                "product_variant_id": str,
                "signals": [
                    {
                        "signal_type": str,
                        "current_value": float,
                        "previous_value": float,
                        "trend_direction": str,  # "up", "stable", "down"
                        "trend_percentage": float,
                        "signal_weight": float,
                    },
                    ...
                ],
                "overall_score": float,
            }
        """
        signals = []

        # 销售趋势
        sales_signals = await self._get_sales_signals(db, product_variant_id, lookback_days)
        signals.extend(sales_signals)

        # 利润趋势
        profit_signals = await self._get_profit_signals(db, product_variant_id, lookback_days)
        signals.extend(profit_signals)

        # 库存覆盖天数
        inventory_signals = await self._get_inventory_signals(db, product_variant_id)
        signals.extend(inventory_signals)

        # 内容表现信号
        content_signals = await self._get_content_signals(db, product_variant_id, lookback_days)
        signals.extend(content_signals)

        # 计算总体评分
        overall_score = self._calculate_overall_score(signals)

        return {
            "product_variant_id": str(product_variant_id),
            "signals": signals,
            "overall_score": overall_score,
        }

    async def _get_sales_signals(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        lookback_days: int,
    ) -> list[dict]:
        """获取销售趋势信号。"""
        # Query recent 7 days vs prior 7-14 days revenue
        today = date.today()
        recent_end = today
        recent_start = today - timedelta(days=7)
        prior_end = recent_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=7)

        # Recent period revenue
        recent_stmt = (
            select(func.sum(ProfitLedger.gross_revenue))
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= recent_start)
            .where(ProfitLedger.snapshot_date <= recent_end)
        )
        recent_result = await db.execute(recent_stmt)
        recent_revenue = recent_result.scalar() or Decimal("0")

        # Prior period revenue
        prior_stmt = (
            select(func.sum(ProfitLedger.gross_revenue))
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= prior_start)
            .where(ProfitLedger.snapshot_date <= prior_end)
        )
        prior_result = await db.execute(prior_stmt)
        prior_revenue = prior_result.scalar() or Decimal("0")

        # Calculate trend
        trend_direction = "stable"
        trend_percentage = 0.0

        if prior_revenue > 0:
            change = (recent_revenue - prior_revenue) / prior_revenue
            trend_percentage = float(change * 100)
            if change > 0.05:
                trend_direction = "up"
            elif change < -0.05:
                trend_direction = "down"
        elif recent_revenue > 0:
            trend_direction = "up"
            trend_percentage = 100.0

        return [{
            "signal_type": "sales_trend",
            "current_value": float(recent_revenue),
            "previous_value": float(prior_revenue),
            "trend_direction": trend_direction,
            "trend_percentage": trend_percentage,
            "signal_weight": 1.5,
        }]

    async def _get_profit_signals(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        lookback_days: int,
    ) -> list[dict]:
        """获取利润趋势信号。"""
        today = date.today()
        recent_end = today
        recent_start = today - timedelta(days=7)
        prior_end = recent_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=7)

        # Recent period profit margin
        recent_stmt = (
            select(func.avg(ProfitLedger.profit_margin))
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= recent_start)
            .where(ProfitLedger.snapshot_date <= recent_end)
        )
        recent_result = await db.execute(recent_stmt)
        recent_margin = recent_result.scalar() or Decimal("0")

        # Prior period profit margin
        prior_stmt = (
            select(func.avg(ProfitLedger.profit_margin))
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= prior_start)
            .where(ProfitLedger.snapshot_date <= prior_end)
        )
        prior_result = await db.execute(prior_stmt)
        prior_margin = prior_result.scalar() or Decimal("0")

        # Calculate trend
        trend_direction = "stable"
        trend_percentage = 0.0

        if prior_margin > 0:
            change = (recent_margin - prior_margin) / prior_margin
            trend_percentage = float(change * 100)
            if change > 0.05:
                trend_direction = "up"
            elif change < -0.05:
                trend_direction = "down"
        elif recent_margin > 0:
            trend_direction = "up"
            trend_percentage = 100.0

        return [{
            "signal_type": "profit_margin_trend",
            "current_value": float(recent_margin),
            "previous_value": float(prior_margin),
            "trend_direction": trend_direction,
            "trend_percentage": trend_percentage,
            "signal_weight": 1.5,
        }]

    async def _get_inventory_signals(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
    ) -> list[dict]:
        """获取库存覆盖天数信号。"""
        # Query inventory level
        stmt = select(InventoryLevel).where(
            InventoryLevel.variant_id == product_variant_id
        )
        result = await db.execute(stmt)
        inventory = result.scalar_one_or_none()

        available = inventory.available_quantity if inventory else 0

        # Estimate average daily sales from recent profit_ledger
        today = date.today()
        start_date = today - timedelta(days=14)

        sales_stmt = (
            select(func.sum(ProfitLedger.gross_revenue))
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= start_date)
        )
        sales_result = await db.execute(sales_stmt)
        total_revenue = sales_result.scalar() or Decimal("0")
        avg_daily_revenue = total_revenue / 14 if total_revenue > 0 else Decimal("0")

        # Estimate coverage days
        coverage_days = 0
        if avg_daily_revenue > 0:
            # Assume average unit price of $20 for rough estimation
            estimated_avg_price = Decimal("20")
            daily_units = avg_daily_revenue / estimated_avg_price
            coverage_days = int(available / daily_units) if daily_units > 0 else 0

        return [{
            "signal_type": "inventory_coverage_days",
            "current_value": float(coverage_days),
            "previous_value": 0.0,
            "trend_direction": "stable",
            "trend_percentage": 0.0,
            "signal_weight": 1.0,
        }]

    async def _get_content_signals(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        lookback_days: int,
    ) -> list[dict]:
        """获取内容表现信号（CTR, CVR）。"""
        today = date.today()
        recent_end = today
        recent_start = today - timedelta(days=7)
        prior_end = recent_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=7)

        # Get all listings for this variant
        listings_stmt = select(PlatformListing.id).where(
            PlatformListing.product_variant_id == product_variant_id
        )
        listings_result = await db.execute(listings_stmt)
        listing_ids = [row[0] for row in listings_result.fetchall()]

        if not listing_ids:
            return []

        # Recent CTR
        recent_stmt = (
            select(
                func.sum(ListingPerformanceDaily.impressions).label("impressions"),
                func.sum(ListingPerformanceDaily.clicks).label("clicks"),
            )
            .where(ListingPerformanceDaily.listing_id.in_(listing_ids))
            .where(ListingPerformanceDaily.metric_date >= recent_start)
            .where(ListingPerformanceDaily.metric_date <= recent_end)
        )
        recent_result = await db.execute(recent_stmt)
        recent_row = recent_result.fetchone()

        # Prior CTR
        prior_stmt = (
            select(
                func.sum(ListingPerformanceDaily.impressions).label("impressions"),
                func.sum(ListingPerformanceDaily.clicks).label("clicks"),
            )
            .where(ListingPerformanceDaily.listing_id.in_(listing_ids))
            .where(ListingPerformanceDaily.metric_date >= prior_start)
            .where(ListingPerformanceDaily.metric_date <= prior_end)
        )
        prior_result = await db.execute(prior_stmt)
        prior_row = prior_result.fetchone()

        signals = []

        if recent_row and prior_row:
            recent_impressions = recent_row.impressions or 0
            recent_clicks = recent_row.clicks or 0
            prior_impressions = prior_row.impressions or 0
            prior_clicks = prior_row.clicks or 0

            recent_ctr = float(recent_clicks) / recent_impressions if recent_impressions > 0 else 0.0
            prior_ctr = float(prior_clicks) / prior_impressions if prior_impressions > 0 else 0.0

            ctr_trend = "stable"
            ctr_trend_pct = 0.0
            if prior_ctr > 0:
                ctr_change = (recent_ctr - prior_ctr) / prior_ctr
                ctr_trend_pct = ctr_change * 100
                if ctr_change > 0.05:
                    ctr_trend = "up"
                elif ctr_change < -0.05:
                    ctr_trend = "down"

            signals.append({
                "signal_type": "ctr_trend",
                "current_value": recent_ctr * 100,
                "previous_value": prior_ctr * 100,
                "trend_direction": ctr_trend,
                "trend_percentage": ctr_trend_pct,
                "signal_weight": 1.0,
            })

            # CVR signal
            recent_orders_stmt = (
                select(func.sum(ListingPerformanceDaily.orders).label("orders"))
                .where(ListingPerformanceDaily.listing_id.in_(listing_ids))
                .where(ListingPerformanceDaily.metric_date >= recent_start)
                .where(ListingPerformanceDaily.metric_date <= recent_end)
            )
            recent_orders_result = await db.execute(recent_orders_stmt)
            recent_orders = recent_orders_result.scalar() or 0

            prior_orders_stmt = (
                select(func.sum(ListingPerformanceDaily.orders).label("orders"))
                .where(ListingPerformanceDaily.listing_id.in_(listing_ids))
                .where(ListingPerformanceDaily.metric_date >= prior_start)
                .where(ListingPerformanceDaily.metric_date <= prior_end)
            )
            prior_orders_result = await db.execute(prior_orders_stmt)
            prior_orders = prior_orders_result.scalar() or 0

            recent_cvr = float(recent_orders) / recent_clicks if recent_clicks > 0 else 0.0
            prior_cvr = float(prior_orders) / prior_clicks if prior_clicks > 0 else 0.0

            cvr_trend = "stable"
            cvr_trend_pct = 0.0
            if prior_cvr > 0:
                cvr_change = (recent_cvr - prior_cvr) / prior_cvr
                cvr_trend_pct = cvr_change * 100
                if cvr_change > 0.05:
                    cvr_trend = "up"
                elif cvr_change < -0.05:
                    cvr_trend = "down"

            signals.append({
                "signal_type": "cvr_trend",
                "current_value": recent_cvr * 100,
                "previous_value": prior_cvr * 100,
                "trend_direction": cvr_trend,
                "trend_percentage": cvr_trend_pct,
                "signal_weight": 1.0,
            })

        return signals

    def _calculate_overall_score(self, signals: list[dict]) -> float:
        """计算总体评分（0-100）。"""
        if not signals:
            return 50.0

        total_weight = sum(s.get("signal_weight", 1.0) for s in signals)
        weighted_score = 0.0

        for signal in signals:
            weight = signal.get("signal_weight", 1.0)
            value = signal.get("current_value", 50.0)
            weighted_score += value * weight

        return weighted_score / total_weight if total_weight > 0 else 50.0
