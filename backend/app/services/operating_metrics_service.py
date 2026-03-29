"""Operating metrics service for unified read-only aggregation layer."""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.listing_metrics_service import ListingMetricsService
from app.services.profit_ledger_service import ProfitLedgerService
from app.services.refund_analysis_service import RefundAnalysisService


class OperatingMetricsService:
    """Unified read-only aggregation layer for operating metrics."""

    def __init__(self):
        self.logger = get_logger(__name__)
        self.profit_service = ProfitLedgerService()
        self.refund_service = RefundAnalysisService()
        self.listing_metrics_service = ListingMetricsService()

    async def get_sku_operating_snapshot(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get SKU-level operating snapshot.

        Args:
            db: Database session
            product_variant_id: Product variant ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            {
                "profit_snapshot": {...},
                "refund_rate": {...},
                "refund_reasons": [...],
            }
        """
        # Get profit snapshot
        profit_snapshot = await self.profit_service.get_profit_snapshot(
            db=db,
            product_variant_id=product_variant_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get refund rate
        refund_rate = await self.refund_service.get_refund_rate(
            db=db,
            product_variant_id=product_variant_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get refund reasons
        refund_reasons = await self.refund_service.summarize_refund_reasons(
            db=db,
            product_variant_id=product_variant_id,
            start_date=start_date,
            end_date=end_date,
        )

        self.logger.info(
            "sku_operating_snapshot_generated",
            variant_id=str(product_variant_id),
            profit_entries=profit_snapshot["entry_count"],
            refund_rate=refund_rate["refund_rate"],
        )

        return {
            "variant_id": str(product_variant_id),
            "profit_snapshot": profit_snapshot,
            "refund_rate": refund_rate,
            "refund_reasons": refund_reasons,
        }

    async def get_listing_operating_snapshot(
        self,
        db: AsyncSession,
        platform_listing_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get listing-level operating snapshot.

        Args:
            db: Database session
            platform_listing_id: Platform listing ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            {
                "profit_snapshot": {...},
                "refund_rate": {...},
                "refund_reasons": [...],
                "listing_performance": {...},
            }
        """
        # Get profit snapshot
        profit_snapshot = await self.profit_service.get_listing_profitability(
            db=db,
            platform_listing_id=platform_listing_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get refund rate
        refund_rate = await self.refund_service.get_refund_rate(
            db=db,
            platform_listing_id=platform_listing_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get refund reasons
        refund_reasons = await self.refund_service.summarize_refund_reasons(
            db=db,
            platform_listing_id=platform_listing_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get listing performance
        listing_performance = await self.listing_metrics_service.get_metrics_summary(
            db=db,
            listing_id=platform_listing_id,
            start_date=start_date,
            end_date=end_date,
        )

        self.logger.info(
            "listing_operating_snapshot_generated",
            listing_id=str(platform_listing_id),
            profit_entries=profit_snapshot["entry_count"],
            refund_rate=refund_rate["refund_rate"],
        )

        return {
            "listing_id": str(platform_listing_id),
            "profit_snapshot": profit_snapshot,
            "refund_rate": refund_rate,
            "refund_reasons": refund_reasons,
            "listing_performance": listing_performance,
        }

    async def get_supplier_operating_snapshot(
        self,
        db: AsyncSession,
        supplier_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get supplier-level operating snapshot.

        Args:
            db: Database session
            supplier_id: Supplier ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            {
                "profit_snapshot": {...},
            }
        """
        # Get profit snapshot
        profit_snapshot = await self.profit_service.get_supplier_profitability(
            db=db,
            supplier_id=supplier_id,
            start_date=start_date,
            end_date=end_date,
        )

        self.logger.info(
            "supplier_operating_snapshot_generated",
            supplier_id=str(supplier_id),
            profit_entries=profit_snapshot["entry_count"],
        )

        return {
            "supplier_id": str(supplier_id),
            "profit_snapshot": profit_snapshot,
        }
