"""异常检测服务，识别 CTR 异常下降、退款异常上升、库存断货风险等经营问题。

Anomaly Detection Service for detecting:
- Sales drop anomalies
- Refund spike anomalies
- Margin collapse anomalies
- Stockout risk anomalies
- CTR drop anomalies
- Conversion rate drop anomalies
- Supplier delay and fulfillment issues
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    PlatformListingStatus,
    ProductVariantStatus,
)
from app.core.logging import get_logger
from app.db.models import (
    AnomalyDetectionSignal,
    InventoryLevel,
    ListingPerformanceDaily,
    PlatformListing,
    ProfitLedger,
    RefundCase,
    Supplier,
    SupplierOffer,
)

logger = get_logger(__name__)


class AnomalyDetectionService:
    """识别经营异常的规则引擎。

    Detects various anomalies in SKU performance, listing metrics,
    and supplier operations.
    """

    # Detection thresholds
    SALES_DROP_THRESHOLD = Decimal("0.30")  # 30% decline
    REFUND_SPIKE_THRESHOLD = Decimal("0.50")  # 50% increase
    MARGIN_COLLAPSE_THRESHOLD = Decimal("0.15")  # Margin below 15%
    STOCKOUT_RISK_DAYS = 7  # Inventory coverage less than 7 days
    SUPPLIER_DELAY_DAYS = 14  # Pending PO over 14 days
    CTR_DROP_THRESHOLD = Decimal("0.30")  # 30% decline
    CVR_DROP_THRESHOLD = Decimal("0.30")  # 30% decline
    MIN_DATA_POINTS = 7  # Minimum data points for comparison

    def __init__(self):
        """Initialize anomaly detection service."""
        pass

    async def detect_sku_anomalies(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        lookback_days: int = 30,
    ) -> list[dict]:
        """Detect all anomalies for a SKU.

        Args:
            db: Database session
            product_variant_id: SKU ID
            lookback_days: Days to look back for analysis

        Returns:
            List of anomalies, each containing type, severity, details
        """
        anomalies = []

        # 1. Sales drop detection
        sales_anomalies = await self._detect_sales_drop(db, product_variant_id, lookback_days)
        anomalies.extend(sales_anomalies)

        # 2. Refund spike detection
        refund_anomalies = await self._detect_refund_spike(db, product_variant_id, lookback_days)
        anomalies.extend(refund_anomalies)

        # 3. Margin collapse detection
        margin_anomalies = await self._detect_margin_collapse(db, product_variant_id, lookback_days)
        anomalies.extend(margin_anomalies)

        # 4. Stockout risk detection
        stockout_anomalies = await self._detect_stockout_risk(db, product_variant_id)
        anomalies.extend(stockout_anomalies)

        logger.info(
            "sku_anomalies_detected",
            product_variant_id=str(product_variant_id),
            anomaly_count=len(anomalies),
            types=[a["type"] for a in anomalies],
        )

        return anomalies

    async def detect_listing_anomalies(
        self,
        db: AsyncSession,
        listing_id: UUID,
        lookback_days: int = 30,
    ) -> list[dict]:
        """Detect anomalies for a specific listing.

        Args:
            db: Database session
            listing_id: Listing ID
            lookback_days: Days to look back for analysis

        Returns:
            List of anomalies
        """
        anomalies = []

        # Query listing
        stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
        result = await db.execute(stmt)
        listing = result.scalar_one_or_none()

        if not listing:
            return anomalies

        # 1. CTR drop detection
        ctr_anomalies = await self._detect_ctr_drop(db, listing, lookback_days)
        anomalies.extend(ctr_anomalies)

        # 2. Conversion rate drop detection
        cvr_anomalies = await self._detect_cvr_drop(db, listing, lookback_days)
        anomalies.extend(cvr_anomalies)

        logger.info(
            "listing_anomalies_detected",
            listing_id=str(listing_id),
            anomaly_count=len(anomalies),
            types=[a["type"] for a in anomalies],
        )

        return anomalies

    async def detect_supplier_anomalies(
        self,
        db: AsyncSession,
        supplier_id: UUID,
    ) -> list[dict]:
        """Detect anomalies for a supplier.

        Args:
            db: Database session
            supplier_id: Supplier ID

        Returns:
            List of anomalies
        """
        anomalies = []

        # 1. Supplier delay risk
        delay_anomalies = await self._detect_supplier_delay(db, supplier_id)
        anomalies.extend(delay_anomalies)

        # 2. Supplier fulfillment issues
        fulfillment_anomalies = await self._detect_supplier_fulfillment_issues(db, supplier_id)
        anomalies.extend(fulfillment_anomalies)

        logger.info(
            "supplier_anomalies_detected",
            supplier_id=str(supplier_id),
            anomaly_count=len(anomalies),
            types=[a["type"] for a in anomalies],
        )

        return anomalies

    async def detect_global_anomalies(
        self,
        db: AsyncSession,
        lookback_days: int = 30,
        limit: int = 100,
    ) -> dict:
        """Detect global anomalies, aggregating across all SKUs/listings.

        Args:
            db: Database session
            lookback_days: Days to look back for analysis
            limit: Maximum number of anomalies to return

        Returns:
            Global anomaly summary with:
            - total_anomalies
            - affected_skus
            - by_type
            - by_severity
            - anomalies (list)
        """
        # Query all active SKUs
        stmt = (
            select(PlatformListing.product_variant_id)
            .where(PlatformListing.status == PlatformListingStatus.ACTIVE)
            .where(PlatformListing.product_variant_id.isnot(None))
            .distinct()
            .limit(limit)
        )
        result = await db.execute(stmt)
        variant_ids = [row[0] for row in result.fetchall()]

        all_anomalies = []
        sku_anomaly_counts = {}

        for variant_id in variant_ids:
            if variant_id is None:
                continue

            sku_anomalies = await self.detect_sku_anomalies(
                db=db,
                product_variant_id=variant_id,
                lookback_days=lookback_days,
            )

            if sku_anomalies:
                sku_anomaly_counts[str(variant_id)] = len(sku_anomalies)
                for anomaly in sku_anomalies:
                    anomaly["product_variant_id"] = str(variant_id)
                    all_anomalies.append(anomaly)

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_anomalies.sort(key=lambda a: severity_order.get(a.get("severity", "low"), 4))

        # Summary statistics
        summary = {
            "total_anomalies": len(all_anomalies),
            "affected_skus": len(sku_anomaly_counts),
            "by_type": {},
            "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "anomalies": all_anomalies[:limit],
        }

        for anomaly in all_anomalies:
            anomaly_type = anomaly.get("type", "unknown")
            severity = anomaly.get("severity", "low")
            summary["by_type"][anomaly_type] = summary["by_type"].get(anomaly_type, 0) + 1
            summary["by_severity"][severity] += 1

        logger.info(
            "global_anomalies_detected",
            total_anomalies=summary["total_anomalies"],
            affected_skus=summary["affected_skus"],
            by_type=summary["by_type"],
        )

        return summary

    async def save_anomaly_signal(
        self,
        db: AsyncSession,
        target_type: str,
        target_id: UUID,
        anomaly_type: str,
        severity: str,
        anomaly_data: dict,
        description: Optional[str] = None,
    ) -> AnomalyDetectionSignal:
        """Save an anomaly detection signal to the database.

        Args:
            db: Database session
            target_type: Type of target (product_variant, platform_listing, supplier)
            target_id: Target ID
            anomaly_type: Type of anomaly
            severity: Severity level (critical, high, medium, low)
            anomaly_data: Anomaly details and metrics
            description: Human-readable description

        Returns:
            Created AnomalyDetectionSignal
        """
        signal = AnomalyDetectionSignal(
            id=uuid4(),
            target_type=target_type,
            target_id=target_id,
            anomaly_type=anomaly_type,
            severity=severity,
            detected_at=datetime.utcnow(),
            anomaly_data=anomaly_data,
            description=description,
            is_resolved=False,
        )
        db.add(signal)
        await db.flush()

        logger.info(
            "anomaly_signal_saved",
            signal_id=str(signal.id),
            target_type=target_type,
            target_id=str(target_id),
            anomaly_type=anomaly_type,
            severity=severity,
        )

        return signal

    async def _detect_sales_drop(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        lookback_days: int,
    ) -> list[dict]:
        """Detect sales drop anomalies.

        Compares recent 7 days vs prior 7-14 days revenue data.
        """
        anomalies = []
        today = date.today()
        recent_end = today
        recent_start = today - timedelta(days=7)
        prior_end = recent_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=7)

        # Query revenue from profit_ledger
        recent_stmt = (
            select(func.sum(ProfitLedger.gross_revenue))
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= recent_start)
            .where(ProfitLedger.snapshot_date <= recent_end)
        )
        recent_result = await db.execute(recent_stmt)
        recent_revenue = recent_result.scalar() or Decimal("0")

        prior_stmt = (
            select(func.sum(ProfitLedger.gross_revenue))
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= prior_start)
            .where(ProfitLedger.snapshot_date <= prior_end)
        )
        prior_result = await db.execute(prior_stmt)
        prior_revenue = prior_result.scalar() or Decimal("0")

        # Check if we have enough data
        if prior_revenue <= Decimal("0"):
            return anomalies

        # Calculate decline percentage
        decline = (prior_revenue - recent_revenue) / prior_revenue

        if decline >= self.SALES_DROP_THRESHOLD:
            severity = self._calculate_severity(decline, self.SALES_DROP_THRESHOLD)

            anomalies.append({
                "type": "sales_drop",
                "severity": severity,
                "details": {
                    "recent_revenue": float(recent_revenue),
                    "prior_revenue": float(prior_revenue),
                    "decline_percentage": float(decline * 100),
                    "threshold_percentage": float(self.SALES_DROP_THRESHOLD * 100),
                    "recent_period": f"{recent_start} to {recent_end}",
                    "prior_period": f"{prior_start} to {prior_end}",
                },
            })

        return anomalies

    async def _detect_refund_spike(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        lookback_days: int,
    ) -> list[dict]:
        """Detect refund spike anomalies.

        Compares refund rate in recent period vs prior period.
        """
        anomalies = []
        today = date.today()
        recent_start = today - timedelta(days=lookback_days // 2)
        prior_start = today - timedelta(days=lookback_days)
        prior_end = recent_start - timedelta(days=1)

        # Query recent refunds
        recent_stmt = (
            select(func.count(RefundCase.id))
            .where(RefundCase.product_variant_id == product_variant_id)
            .where(RefundCase.requested_at >= recent_start)
        )
        recent_result = await db.execute(recent_stmt)
        recent_refunds = recent_result.scalar() or 0

        # Query prior refunds
        prior_stmt = (
            select(func.count(RefundCase.id))
            .where(RefundCase.product_variant_id == product_variant_id)
            .where(RefundCase.requested_at >= prior_start)
            .where(RefundCase.requested_at < prior_end)
        )
        prior_result = await db.execute(prior_stmt)
        prior_refunds = prior_result.scalar() or 0

        if prior_refunds == 0:
            # No prior refunds, check if recent refunds are high
            if recent_refunds >= 3:  # Threshold for new refund cases
                anomalies.append({
                    "type": "refund_spike",
                    "severity": "high",
                    "details": {
                        "recent_refunds": recent_refunds,
                        "prior_refunds": prior_refunds,
                        "increase_type": "new_refund_cases",
                        "recent_period": f"{recent_start} to {today}",
                    },
                })
            return anomalies

        # Calculate increase percentage
        increase = Decimal(recent_refunds - prior_refunds) / Decimal(prior_refunds)

        if increase >= self.REFUND_SPIKE_THRESHOLD:
            severity = self._calculate_severity(increase, self.REFUND_SPIKE_THRESHOLD)

            anomalies.append({
                "type": "refund_spike",
                "severity": severity,
                "details": {
                    "recent_refunds": recent_refunds,
                    "prior_refunds": prior_refunds,
                    "increase_percentage": float(increase * 100),
                    "threshold_percentage": float(self.REFUND_SPIKE_THRESHOLD * 100),
                    "recent_period": f"{recent_start} to {today}",
                    "prior_period": f"{prior_start} to {prior_end}",
                },
            })

        return anomalies

    async def _detect_margin_collapse(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        lookback_days: int,
    ) -> list[dict]:
        """Detect margin collapse anomalies.

        Checks if profit margin has fallen below threshold.
        """
        anomalies = []
        today = date.today()
        start_date = today - timedelta(days=lookback_days)

        # Query profit margins from profit_ledger
        stmt = (
            select(
                func.avg(ProfitLedger.profit_margin).label("avg_margin"),
                func.sum(ProfitLedger.gross_revenue).label("total_revenue"),
                func.sum(ProfitLedger.net_profit).label("total_profit"),
            )
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= start_date)
        )
        result = await db.execute(stmt)
        row = result.fetchone()

        if not row or row.total_revenue is None or row.total_revenue <= 0:
            return anomalies

        avg_margin = row.avg_margin
        total_revenue = row.total_revenue
        total_profit = row.total_profit or Decimal("0")

        # Calculate overall margin
        overall_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else Decimal("0")

        if avg_margin is not None and avg_margin < self.MARGIN_COLLAPSE_THRESHOLD * 100:
            anomalies.append({
                "type": "margin_collapse",
                "severity": "critical",
                "details": {
                    "average_margin": float(avg_margin) if avg_margin else None,
                    "overall_margin": float(overall_margin),
                    "threshold_percentage": float(self.MARGIN_COLLAPSE_THRESHOLD * 100),
                    "total_revenue": float(total_revenue),
                    "total_profit": float(total_profit),
                    "period": f"{start_date} to {today}",
                },
            })

        return anomalies

    async def _detect_stockout_risk(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
    ) -> list[dict]:
        """Detect stockout risk based on inventory levels.

        Checks if inventory can cover expected demand for configured days.
        """
        anomalies = []

        # Query inventory level
        stmt = (
            select(InventoryLevel)
            .where(InventoryLevel.variant_id == product_variant_id)
        )
        result = await db.execute(stmt)
        inventory = result.scalar_one_or_none()

        if not inventory:
            return anomalies

        available = inventory.available_quantity or 0

        # Calculate average daily sales from recent profit_ledger
        today = date.today()
        start_date = today - timedelta(days=14)

        sales_stmt = (
            select(func.sum(ProfitLedger.gross_revenue))
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= start_date)
        )
        sales_result = await db.execute(sales_stmt)
        total_revenue = sales_result.scalar() or Decimal("0")

        # Estimate daily units (rough estimate from revenue)
        # This is a simplification - in reality would need unit sales
        avg_daily_revenue = total_revenue / 14 if total_revenue > 0 else Decimal("0")

        if avg_daily_revenue <= 0:
            return anomalies

        # Estimate days of inventory (using revenue as proxy)
        # This would be better with actual unit sales data
        # For now, assume a minimum threshold for available inventory
        if available <= 0:
            anomalies.append({
                "type": "stockout_risk",
                "severity": "critical",
                "details": {
                    "available_inventory": available,
                    "days_coverage": 0,
                    "threshold_days": self.STOCKOUT_RISK_DAYS,
                    "status": "out_of_stock",
                },
            })
        elif available < 10:  # Low inventory threshold
            anomalies.append({
                "type": "stockout_risk",
                "severity": "high",
                "details": {
                    "available_inventory": available,
                    "threshold_days": self.STOCKOUT_RISK_DAYS,
                    "status": "low_inventory",
                },
            })

        return anomalies

    async def _detect_ctr_drop(
        self,
        db: AsyncSession,
        listing: PlatformListing,
        lookback_days: int,
    ) -> list[dict]:
        """Detect CTR drop anomalies.

        Compares recent CTR vs prior period CTR.
        """
        anomalies = []
        today = date.today()
        recent_end = today
        recent_start = today - timedelta(days=7)
        prior_end = recent_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=7)

        # Query recent CTR
        recent_stmt = (
            select(
                func.sum(ListingPerformanceDaily.impressions).label("impressions"),
                func.sum(ListingPerformanceDaily.clicks).label("clicks"),
            )
            .where(ListingPerformanceDaily.listing_id == listing.id)
            .where(ListingPerformanceDaily.metric_date >= recent_start)
            .where(ListingPerformanceDaily.metric_date <= recent_end)
        )
        recent_result = await db.execute(recent_stmt)
        recent_row = recent_result.fetchone()

        # Query prior CTR
        prior_stmt = (
            select(
                func.sum(ListingPerformanceDaily.impressions).label("impressions"),
                func.sum(ListingPerformanceDaily.clicks).label("clicks"),
            )
            .where(ListingPerformanceDaily.listing_id == listing.id)
            .where(ListingPerformanceDaily.metric_date >= prior_start)
            .where(ListingPerformanceDaily.metric_date <= prior_end)
        )
        prior_result = await db.execute(prior_stmt)
        prior_row = prior_result.fetchone()

        if not recent_row or not prior_row:
            return anomalies

        recent_impressions = recent_row.impressions or 0
        recent_clicks = recent_row.clicks or 0
        prior_impressions = prior_row.impressions or 0
        prior_clicks = prior_row.clicks or 0

        # Need minimum data points
        if recent_impressions < 100 or prior_impressions < 100:
            return anomalies

        recent_ctr = Decimal(recent_clicks) / Decimal(recent_impressions) if recent_impressions > 0 else Decimal("0")
        prior_ctr = Decimal(prior_clicks) / Decimal(prior_impressions) if prior_impressions > 0 else Decimal("0")

        if prior_ctr <= 0:
            return anomalies

        # Calculate decline
        decline = (prior_ctr - recent_ctr) / prior_ctr

        if decline >= self.CTR_DROP_THRESHOLD:
            severity = self._calculate_severity(decline, self.CTR_DROP_THRESHOLD)

            anomalies.append({
                "type": "ctr_drop",
                "severity": severity,
                "details": {
                    "recent_ctr": float(recent_ctr),
                    "prior_ctr": float(prior_ctr),
                    "decline_percentage": float(decline * 100),
                    "threshold_percentage": float(self.CTR_DROP_THRESHOLD * 100),
                    "recent_impressions": recent_impressions,
                    "recent_clicks": recent_clicks,
                    "recent_period": f"{recent_start} to {recent_end}",
                    "prior_period": f"{prior_start} to {prior_end}",
                    "listing_id": str(listing.id),
                    "platform": listing.platform.value if listing.platform else None,
                },
            })

        return anomalies

    async def _detect_cvr_drop(
        self,
        db: AsyncSession,
        listing: PlatformListing,
        lookback_days: int,
    ) -> list[dict]:
        """Detect conversion rate drop anomalies.

        Compares recent CVR vs prior period CVR.
        """
        anomalies = []
        today = date.today()
        recent_end = today
        recent_start = today - timedelta(days=7)
        prior_end = recent_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=7)

        # Query recent CVR
        recent_stmt = (
            select(
                func.sum(ListingPerformanceDaily.clicks).label("clicks"),
                func.sum(ListingPerformanceDaily.orders).label("orders"),
            )
            .where(ListingPerformanceDaily.listing_id == listing.id)
            .where(ListingPerformanceDaily.metric_date >= recent_start)
            .where(ListingPerformanceDaily.metric_date <= recent_end)
        )
        recent_result = await db.execute(recent_stmt)
        recent_row = recent_result.fetchone()

        # Query prior CVR
        prior_stmt = (
            select(
                func.sum(ListingPerformanceDaily.clicks).label("clicks"),
                func.sum(ListingPerformanceDaily.orders).label("orders"),
            )
            .where(ListingPerformanceDaily.listing_id == listing.id)
            .where(ListingPerformanceDaily.metric_date >= prior_start)
            .where(ListingPerformanceDaily.metric_date <= prior_end)
        )
        prior_result = await db.execute(prior_stmt)
        prior_row = prior_result.fetchone()

        if not recent_row or not prior_row:
            return anomalies

        recent_clicks = recent_row.clicks or 0
        recent_orders = recent_row.orders or 0
        prior_clicks = prior_row.clicks or 0
        prior_orders = prior_row.orders or 0

        # Need minimum data points
        if recent_clicks < 50 or prior_clicks < 50:
            return anomalies

        recent_cvr = Decimal(recent_orders) / Decimal(recent_clicks) if recent_clicks > 0 else Decimal("0")
        prior_cvr = Decimal(prior_orders) / Decimal(prior_clicks) if prior_clicks > 0 else Decimal("0")

        if prior_cvr <= 0:
            return anomalies

        # Calculate decline
        decline = (prior_cvr - recent_cvr) / prior_cvr

        if decline >= self.CVR_DROP_THRESHOLD:
            severity = self._calculate_severity(decline, self.CVR_DROP_THRESHOLD)

            anomalies.append({
                "type": "cvr_drop",
                "severity": severity,
                "details": {
                    "recent_cvr": float(recent_cvr),
                    "prior_cvr": float(prior_cvr),
                    "decline_percentage": float(decline * 100),
                    "threshold_percentage": float(self.CVR_DROP_THRESHOLD * 100),
                    "recent_clicks": recent_clicks,
                    "recent_orders": recent_orders,
                    "recent_period": f"{recent_start} to {recent_end}",
                    "prior_period": f"{prior_start} to {prior_end}",
                    "listing_id": str(listing.id),
                    "platform": listing.platform.value if listing.platform else None,
                },
            })

        return anomalies

    async def _detect_supplier_delay(
        self,
        db: AsyncSession,
        supplier_id: UUID,
    ) -> list[dict]:
        """Detect supplier delay risk.

        Checks for pending purchase orders older than threshold.
        """
        anomalies = []

        # Import PurchaseOrderStatus here to avoid circular imports
        from app.core.enums import PurchaseOrderStatus

        # Query for delayed pending purchase orders
        from app.db.models import PurchaseOrder

        threshold_date = datetime.utcnow() - timedelta(days=self.SUPPLIER_DELAY_DAYS)

        stmt = (
            select(func.count(PurchaseOrder.id))
            .where(PurchaseOrder.supplier_id == supplier_id)
            .where(PurchaseOrder.status == PurchaseOrderStatus.SUBMITTED)
            .where(PurchaseOrder.order_date < threshold_date)
        )
        result = await db.execute(stmt)
        delayed_orders = result.scalar() or 0

        if delayed_orders > 0:
            severity = "critical" if delayed_orders >= 3 else "high"

            anomalies.append({
                "type": "supplier_delay",
                "severity": severity,
                "details": {
                    "delayed_orders": delayed_orders,
                    "threshold_days": self.SUPPLIER_DELAY_DAYS,
                    "threshold_date": threshold_date.isoformat(),
                    "supplier_id": str(supplier_id),
                },
            })

        return anomalies

    async def _detect_supplier_fulfillment_issues(
        self,
        db: AsyncSession,
        supplier_id: UUID,
    ) -> list[dict]:
        """Detect supplier fulfillment issues.

        Checks for high refund rates and quality issues.
        """
        anomalies = []

        # Get all variants from this supplier via supplier_offers
        stmt = (
            select(SupplierOffer.variant_id)
            .where(SupplierOffer.supplier_id == supplier_id)
        )
        result = await db.execute(stmt)
        variant_ids = [row[0] for row in result.fetchall()]

        if not variant_ids:
            return anomalies

        # Check refund rate for these variants
        today = date.today()
        start_date = today - timedelta(days=30)

        # Count total orders and refunds
        refunds_stmt = (
            select(func.count(RefundCase.id))
            .where(RefundCase.product_variant_id.in_(variant_ids))
            .where(RefundCase.requested_at >= start_date)
        )
        refunds_result = await db.execute(refunds_stmt)
        refund_count = refunds_result.scalar() or 0

        # Calculate refund rate (simplified - would need order count for proper rate)
        if refund_count >= 5:  # Threshold for concern
            anomalies.append({
                "type": "supplier_fulfillment_issues",
                "severity": "high",
                "details": {
                    "refund_count": refund_count,
                    "period": f"{start_date} to {today}",
                    "affected_variants": len(variant_ids),
                    "supplier_id": str(supplier_id),
                },
            })

        return anomalies

    def _calculate_severity(self, value: Decimal, threshold: Decimal) -> str:
        """Calculate severity based on how much the value exceeds threshold.

        Args:
            value: The actual value (e.g., decline percentage)
            threshold: The threshold value

        Returns:
            Severity level: critical, high, medium, or low
        """
        ratio = value / threshold

        if ratio >= 2.0:
            return "critical"
        elif ratio >= 1.5:
            return "high"
        elif ratio >= 1.2:
            return "medium"
        else:
            return "low"