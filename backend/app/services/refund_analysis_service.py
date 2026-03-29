"""Refund analysis service for refund case tracking."""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RefundReason, RefundStatus
from app.core.logging import get_logger
from app.db.models import PlatformOrder, PlatformOrderLine, ProductVariant, RefundCase

logger = get_logger(__name__)


class RefundAnalysisService:
    """Service for analyzing and persisting refund cases."""

    def __init__(self):
        self.logger = get_logger(__name__)

    async def create_refund_case(
        self,
        db: AsyncSession,
        platform_order_id: UUID,
        refund_amount: Decimal,
        currency: str,
        refund_reason: RefundReason,
        platform_order_line_id: Optional[UUID] = None,
        product_variant_id: Optional[UUID] = None,
        issue_type: Optional[str] = None,
        attributed_to: Optional[str] = None,
        requested_at: Optional[datetime] = None,
    ) -> RefundCase:
        """Create a refund case.

        Args:
            db: Database session
            platform_order_id: Platform order ID
            refund_amount: Refund amount
            currency: Currency code
            refund_reason: Refund reason enum
            platform_order_line_id: Optional order line ID
            product_variant_id: Optional product variant ID
            issue_type: Optional issue type classification
            attributed_to: Optional attribution
            requested_at: Optional request timestamp

        Returns:
            Created RefundCase instance
        """
        refund_case = RefundCase(
            id=uuid4(),
            platform_order_id=platform_order_id,
            platform_order_line_id=platform_order_line_id,
            product_variant_id=product_variant_id,
            refund_amount=refund_amount,
            currency=currency,
            refund_reason=refund_reason,
            refund_status=RefundStatus.PENDING,
            requested_at=requested_at or datetime.now(timezone.utc),
            issue_type=issue_type,
            attributed_to=attributed_to,
        )

        db.add(refund_case)
        await db.commit()
        await db.refresh(refund_case)

        self.logger.info(
            "refund_case_created",
            refund_case_id=str(refund_case.id),
            platform_order_id=str(platform_order_id),
            refund_amount=float(refund_amount),
            refund_reason=refund_reason.value,
        )

        return refund_case

    async def update_refund_status(
        self,
        db: AsyncSession,
        refund_case_id: UUID,
        new_status: RefundStatus,
    ) -> RefundCase:
        """Update refund case status.

        Args:
            db: Database session
            refund_case_id: Refund case ID
            new_status: New refund status

        Returns:
            Updated RefundCase instance
        """
        refund_case = await db.get(RefundCase, refund_case_id)
        if not refund_case:
            raise ValueError(f"Refund case {refund_case_id} not found")

        refund_case.refund_status = new_status
        if new_status == RefundStatus.COMPLETED:
            refund_case.resolved_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(refund_case)

        self.logger.info(
            "refund_status_updated",
            refund_case_id=str(refund_case_id),
            new_status=new_status.value,
        )

        return refund_case

    async def get_refund_rate(
        self,
        db: AsyncSession,
        product_variant_id: Optional[UUID] = None,
        platform_listing_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Calculate refund rate for SKU/listing.

        Args:
            db: Database session
            product_variant_id: Filter by variant ID
            platform_listing_id: Filter by listing ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            {
                "total_orders": int,
                "refunded_orders": int,
                "refund_rate": float,  # percentage
                "total_refund_amount": Decimal,
            }
        """
        # Build query for refund cases
        refund_stmt = select(RefundCase)

        if product_variant_id:
            refund_stmt = refund_stmt.where(RefundCase.product_variant_id == product_variant_id)

        if platform_listing_id:
            refund_stmt = refund_stmt.join(
                PlatformOrderLine, PlatformOrderLine.id == RefundCase.platform_order_line_id
            ).where(PlatformOrderLine.platform_listing_id == platform_listing_id)

        if start_date:
            refund_stmt = refund_stmt.where(RefundCase.requested_at >= datetime.combine(start_date, datetime.min.time()))

        if end_date:
            refund_stmt = refund_stmt.where(
                RefundCase.requested_at <= datetime.combine(end_date, datetime.max.time())
            )

        refund_result = await db.execute(refund_stmt)
        refund_cases = list(refund_result.scalars().all())

        # Get unique order IDs with refunds
        refunded_order_ids = {case.platform_order_id for case in refund_cases}
        refunded_orders = len(refunded_order_ids)

        # Calculate total refund amount
        total_refund_amount = sum((case.refund_amount for case in refund_cases), Decimal("0.00"))

        # Build query for total orders
        order_stmt = select(func.count(func.distinct(PlatformOrder.id))).select_from(PlatformOrder)

        if product_variant_id or platform_listing_id:
            order_stmt = order_stmt.join(PlatformOrderLine, PlatformOrderLine.order_id == PlatformOrder.id)

            if product_variant_id:
                order_stmt = order_stmt.where(PlatformOrderLine.product_variant_id == product_variant_id)

            if platform_listing_id:
                order_stmt = order_stmt.where(PlatformOrderLine.platform_listing_id == platform_listing_id)

        if start_date:
            order_stmt = order_stmt.where(PlatformOrder.ordered_at >= datetime.combine(start_date, datetime.min.time()))

        if end_date:
            order_stmt = order_stmt.where(PlatformOrder.ordered_at <= datetime.combine(end_date, datetime.max.time()))

        order_result = await db.execute(order_stmt)
        total_orders = order_result.scalar() or 0

        # Calculate refund rate
        refund_rate = 0.0
        if total_orders > 0:
            refund_rate = (refunded_orders / total_orders) * 100

        return {
            "total_orders": total_orders,
            "refunded_orders": refunded_orders,
            "refund_rate": round(refund_rate, 2),
            "total_refund_amount": float(total_refund_amount),
        }

    async def summarize_refund_reasons(
        self,
        db: AsyncSession,
        product_variant_id: Optional[UUID] = None,
        platform_listing_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[dict]:
        """Summarize refund reasons distribution.

        Args:
            db: Database session
            product_variant_id: Filter by variant ID
            platform_listing_id: Filter by listing ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            [
                {
                    "refund_reason": RefundReason,
                    "count": int,
                    "total_amount": Decimal,
                    "attributed_to": str,
                },
                ...
            ]
        """
        # Build query
        stmt = select(RefundCase)

        if product_variant_id:
            stmt = stmt.where(RefundCase.product_variant_id == product_variant_id)

        if platform_listing_id:
            stmt = stmt.join(PlatformOrderLine, PlatformOrderLine.id == RefundCase.platform_order_line_id).where(
                PlatformOrderLine.platform_listing_id == platform_listing_id
            )

        if start_date:
            stmt = stmt.where(RefundCase.requested_at >= datetime.combine(start_date, datetime.min.time()))

        if end_date:
            stmt = stmt.where(RefundCase.requested_at <= datetime.combine(end_date, datetime.max.time()))

        result = await db.execute(stmt)
        refund_cases = list(result.scalars().all())

        # Group by refund_reason and attributed_to
        reason_stats: dict[tuple[RefundReason, str], dict] = {}

        for case in refund_cases:
            key = (case.refund_reason, case.attributed_to or "unknown")
            if key not in reason_stats:
                reason_stats[key] = {
                    "refund_reason": case.refund_reason.value,
                    "attributed_to": case.attributed_to or "unknown",
                    "count": 0,
                    "total_amount": Decimal("0.00"),
                }
            reason_stats[key]["count"] += 1
            reason_stats[key]["total_amount"] += case.refund_amount

        # Convert to list and sort by count descending
        summary = list(reason_stats.values())
        summary.sort(key=lambda x: x["count"], reverse=True)

        # Convert Decimal to float for JSON serialization
        for item in summary:
            item["total_amount"] = float(item["total_amount"])

        return summary

    async def link_refund_to_profit_ledger(
        self,
        db: AsyncSession,
        refund_case_id: UUID,
    ) -> "ProfitLedger":  # type: ignore
        """Link refund case to profit ledger and update refund_loss.

        Automatically calls ProfitLedgerService.apply_refund_adjustment().

        Args:
            db: Database session
            refund_case_id: Refund case ID

        Returns:
            Updated ProfitLedger instance

        Raises:
            ValueError: If refund case not found or no profit ledger exists
        """
        from app.db.models import ProfitLedger
        from app.services.profit_ledger_service import ProfitLedgerService

        # Get refund case
        refund_case = await db.get(RefundCase, refund_case_id)
        if not refund_case:
            raise ValueError(f"Refund case {refund_case_id} not found")

        if not refund_case.platform_order_line_id:
            raise ValueError(f"Refund case {refund_case_id} has no order line mapping")

        # Find profit ledger entry
        ledger_stmt = select(ProfitLedger).where(
            ProfitLedger.platform_order_line_id == refund_case.platform_order_line_id
        )
        ledger_result = await db.execute(ledger_stmt)
        ledger = ledger_result.scalar_one_or_none()

        if not ledger:
            raise ValueError(
                f"No profit ledger found for order line {refund_case.platform_order_line_id}"
            )

        # Apply refund adjustment
        profit_service = ProfitLedgerService()
        updated_ledger = await profit_service.apply_refund_adjustment(
            db=db,
            ledger_id=ledger.id,
            refund_amount=refund_case.refund_amount,
        )

        self.logger.info(
            "refund_linked_to_profit_ledger",
            refund_case_id=str(refund_case_id),
            ledger_id=str(updated_ledger.id),
            refund_amount=float(refund_case.refund_amount),
        )

        return updated_ledger
