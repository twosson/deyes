"""Profit ledger service for true profit tracking."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TargetPlatform
from app.core.logging import get_logger
from app.db.models import (
    PlatformListing,
    PlatformOrderLine,
    ProductVariant,
    ProfitLedger,
    SupplierOffer,
)

if TYPE_CHECKING:
    from app.db.models import Supplier

logger = get_logger(__name__)


class ProfitLedgerService:
    """Service for building true profit ledger entries."""

    def __init__(self):
        self.logger = get_logger(__name__)

    async def build_order_profit_ledger(
        self,
        db: AsyncSession,
        order_line_id: UUID,
    ) -> ProfitLedger:
        """Build profit ledger entry from order line.

        Args:
            db: Database session
            order_line_id: Order line ID

        Returns:
            ProfitLedger instance

        Raises:
            ValueError: If order line not found or missing required data
        """
        # Get order line
        order_line = await db.get(PlatformOrderLine, order_line_id)
        if not order_line:
            raise ValueError(f"Order line {order_line_id} not found")

        if not order_line.product_variant_id:
            raise ValueError(f"Order line {order_line_id} has no variant mapping")

        # Get variant
        variant = await db.get(ProductVariant, order_line.product_variant_id)
        if not variant:
            raise ValueError(f"Variant {order_line.product_variant_id} not found")

        # Get supplier cost from SupplierOffer
        offer_stmt = select(SupplierOffer).where(SupplierOffer.variant_id == variant.id)
        offer_result = await db.execute(offer_stmt)
        offer = offer_result.scalar_one_or_none()

        supplier_cost = Decimal("0.00")
        if offer:
            supplier_cost = offer.unit_price * order_line.quantity

        # Get platform listing for commission rate
        listing = None
        if order_line.platform_listing_id:
            listing = await db.get(PlatformListing, order_line.platform_listing_id)

        # Calculate platform fee (assume 10% commission if no listing)
        commission_rate = Decimal("0.10")  # Default 10%
        platform_fee = order_line.gross_revenue * commission_rate

        # Calculate net profit
        net_profit = order_line.gross_revenue - supplier_cost - platform_fee

        # Calculate profit margin
        profit_margin = None
        if order_line.gross_revenue > Decimal("0"):
            profit_margin = (net_profit / order_line.gross_revenue * 100).quantize(Decimal("0.01"))

        # Check if ledger entry already exists
        existing_stmt = select(ProfitLedger).where(
            and_(
                ProfitLedger.product_variant_id == variant.id,
                ProfitLedger.platform_order_line_id == order_line_id,
            )
        )
        existing_result = await db.execute(existing_stmt)
        existing_ledger = existing_result.scalar_one_or_none()

        if existing_ledger:
            # Update existing entry
            existing_ledger.gross_revenue = order_line.gross_revenue
            existing_ledger.platform_fee = platform_fee
            existing_ledger.net_profit = net_profit
            existing_ledger.profit_margin = profit_margin
            await db.commit()
            await db.refresh(existing_ledger)

            self.logger.info(
                "profit_ledger_updated",
                ledger_id=str(existing_ledger.id),
                order_line_id=str(order_line_id),
                net_profit=float(net_profit),
            )

            return existing_ledger

        # Create new ledger entry
        ledger = ProfitLedger(
            id=uuid4(),
            product_variant_id=variant.id,
            platform_order_line_id=order_line_id,
            platform_listing_id=order_line.platform_listing_id,
            gross_revenue=order_line.gross_revenue,
            platform_fee=platform_fee,
            refund_loss=Decimal("0.00"),
            ad_cost=Decimal("0.00"),
            fulfillment_cost=Decimal("0.00"),
            net_profit=net_profit,
            profit_margin=profit_margin,
            snapshot_date=date.today(),
        )

        db.add(ledger)
        await db.commit()
        await db.refresh(ledger)

        self.logger.info(
            "profit_ledger_created",
            ledger_id=str(ledger.id),
            order_line_id=str(order_line_id),
            variant_id=str(variant.id),
            net_profit=float(net_profit),
            profit_margin=float(profit_margin) if profit_margin else None,
        )

        return ledger

    async def apply_refund_adjustment(
        self,
        db: AsyncSession,
        ledger_id: UUID,
        refund_amount: Decimal,
    ) -> ProfitLedger:
        """Apply refund to existing ledger entry.

        Args:
            db: Database session
            ledger_id: Ledger ID
            refund_amount: Refund amount

        Returns:
            Updated ProfitLedger instance

        Raises:
            ValueError: If ledger not found
        """
        ledger = await db.get(ProfitLedger, ledger_id)
        if not ledger:
            raise ValueError(f"Profit ledger {ledger_id} not found")

        # Update refund loss
        ledger.refund_loss += refund_amount

        # Recalculate net profit
        ledger.net_profit = (
            ledger.gross_revenue
            - ledger.platform_fee
            - ledger.refund_loss
            - ledger.ad_cost
            - ledger.fulfillment_cost
        )

        # Recalculate profit margin
        if ledger.gross_revenue > Decimal("0"):
            ledger.profit_margin = (ledger.net_profit / ledger.gross_revenue * 100).quantize(
                Decimal("0.01")
            )
        else:
            ledger.profit_margin = None

        await db.commit()
        await db.refresh(ledger)

        self.logger.info(
            "refund_applied_to_ledger",
            ledger_id=str(ledger_id),
            refund_amount=float(refund_amount),
            new_net_profit=float(ledger.net_profit),
        )

        return ledger

    async def get_profit_snapshot(
        self,
        db: AsyncSession,
        product_variant_id: Optional[UUID] = None,
        listing_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get aggregated profit snapshot.

        Args:
            db: Database session
            product_variant_id: Filter by variant ID
            listing_id: Filter by listing ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Aggregated profit snapshot
        """
        # Build query
        stmt = select(ProfitLedger)

        if product_variant_id:
            stmt = stmt.where(ProfitLedger.product_variant_id == product_variant_id)

        if listing_id:
            stmt = stmt.where(ProfitLedger.platform_listing_id == listing_id)

        if start_date:
            stmt = stmt.where(ProfitLedger.snapshot_date >= start_date)

        if end_date:
            stmt = stmt.where(ProfitLedger.snapshot_date <= end_date)

        result = await db.execute(stmt)
        ledgers = list(result.scalars().all())

        # Aggregate
        total_gross_revenue = sum((ledger.gross_revenue for ledger in ledgers), Decimal("0.00"))
        total_platform_fee = sum((ledger.platform_fee for ledger in ledgers), Decimal("0.00"))
        total_refund_loss = sum((ledger.refund_loss for ledger in ledgers), Decimal("0.00"))
        total_ad_cost = sum((ledger.ad_cost for ledger in ledgers), Decimal("0.00"))
        total_fulfillment_cost = sum((ledger.fulfillment_cost for ledger in ledgers), Decimal("0.00"))
        total_net_profit = sum((ledger.net_profit for ledger in ledgers), Decimal("0.00"))

        # Calculate overall margin
        overall_margin = None
        if total_gross_revenue > Decimal("0"):
            overall_margin = (total_net_profit / total_gross_revenue * 100).quantize(Decimal("0.01"))

        return {
            "entry_count": len(ledgers),
            "total_gross_revenue": float(total_gross_revenue),
            "total_platform_fee": float(total_platform_fee),
            "total_refund_loss": float(total_refund_loss),
            "total_ad_cost": float(total_ad_cost),
            "total_fulfillment_cost": float(total_fulfillment_cost),
            "total_net_profit": float(total_net_profit),
            "overall_margin": float(overall_margin) if overall_margin else None,
        }

    async def allocate_ad_cost(
        self,
        db: AsyncSession,
        platform_listing_id: UUID,
        ad_cost: Decimal,
        allocation_date: date,
    ) -> list[ProfitLedger]:
        """Allocate ad cost to profit ledger entries.

        Strategy: Proportional to gross_revenue within allocation_date.

        Args:
            db: Database session
            platform_listing_id: Listing ID
            ad_cost: Total ad cost to allocate
            allocation_date: Date for allocation

        Returns:
            List of updated ProfitLedger instances
        """
        # Get all ledger entries for this listing on this date
        stmt = select(ProfitLedger).where(
            and_(
                ProfitLedger.platform_listing_id == platform_listing_id,
                ProfitLedger.snapshot_date == allocation_date,
            )
        )
        result = await db.execute(stmt)
        ledgers = list(result.scalars().all())

        if not ledgers:
            self.logger.warning(
                "no_ledger_entries_for_ad_allocation",
                listing_id=str(platform_listing_id),
                allocation_date=str(allocation_date),
            )
            return []

        # Calculate total revenue for proportional allocation
        total_revenue = sum((ledger.gross_revenue for ledger in ledgers), Decimal("0.00"))

        if total_revenue == Decimal("0.00"):
            self.logger.warning(
                "zero_revenue_for_ad_allocation",
                listing_id=str(platform_listing_id),
                allocation_date=str(allocation_date),
            )
            return []

        # Allocate ad cost proportionally
        updated_ledgers = []
        for ledger in ledgers:
            proportion = ledger.gross_revenue / total_revenue
            allocated_ad_cost = (ad_cost * proportion).quantize(Decimal("0.01"))

            ledger.ad_cost += allocated_ad_cost

            # Recalculate net profit
            ledger.net_profit = (
                ledger.gross_revenue
                - ledger.platform_fee
                - ledger.refund_loss
                - ledger.ad_cost
                - ledger.fulfillment_cost
            )

            # Recalculate profit margin
            if ledger.gross_revenue > Decimal("0"):
                ledger.profit_margin = (ledger.net_profit / ledger.gross_revenue * 100).quantize(
                    Decimal("0.01")
                )
            else:
                ledger.profit_margin = None

            updated_ledgers.append(ledger)

        await db.commit()

        self.logger.info(
            "ad_cost_allocated",
            listing_id=str(platform_listing_id),
            allocation_date=str(allocation_date),
            ad_cost=float(ad_cost),
            ledger_count=len(updated_ledgers),
        )

        return updated_ledgers

    async def get_supplier_profitability(
        self,
        db: AsyncSession,
        supplier_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get supplier-level profitability snapshot.

        Args:
            db: Database session
            supplier_id: Supplier ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Aggregated profitability snapshot
        """
        # Get all variants supplied by this supplier
        from app.db.models import Supplier

        supplier = await db.get(Supplier, supplier_id)
        if not supplier:
            raise ValueError(f"Supplier {supplier_id} not found")

        # Get all offers from this supplier
        offer_stmt = select(SupplierOffer.variant_id).where(SupplierOffer.supplier_id == supplier_id)
        offer_result = await db.execute(offer_stmt)
        variant_ids = [row[0] for row in offer_result.all()]

        if not variant_ids:
            return {
                "supplier_id": str(supplier_id),
                "supplier_name": supplier.name,
                "entry_count": 0,
                "total_gross_revenue": 0.0,
                "total_platform_fee": 0.0,
                "total_refund_loss": 0.0,
                "total_ad_cost": 0.0,
                "total_fulfillment_cost": 0.0,
                "total_net_profit": 0.0,
                "overall_margin": None,
            }

        # Build query for profit ledgers
        stmt = select(ProfitLedger).where(ProfitLedger.product_variant_id.in_(variant_ids))

        if start_date:
            stmt = stmt.where(ProfitLedger.snapshot_date >= start_date)

        if end_date:
            stmt = stmt.where(ProfitLedger.snapshot_date <= end_date)

        result = await db.execute(stmt)
        ledgers = list(result.scalars().all())

        # Aggregate
        total_gross_revenue = sum((ledger.gross_revenue for ledger in ledgers), Decimal("0.00"))
        total_platform_fee = sum((ledger.platform_fee for ledger in ledgers), Decimal("0.00"))
        total_refund_loss = sum((ledger.refund_loss for ledger in ledgers), Decimal("0.00"))
        total_ad_cost = sum((ledger.ad_cost for ledger in ledgers), Decimal("0.00"))
        total_fulfillment_cost = sum((ledger.fulfillment_cost for ledger in ledgers), Decimal("0.00"))
        total_net_profit = sum((ledger.net_profit for ledger in ledgers), Decimal("0.00"))

        # Calculate overall margin
        overall_margin = None
        if total_gross_revenue > Decimal("0"):
            overall_margin = (total_net_profit / total_gross_revenue * 100).quantize(Decimal("0.01"))

        return {
            "supplier_id": str(supplier_id),
            "supplier_name": supplier.name,
            "entry_count": len(ledgers),
            "total_gross_revenue": float(total_gross_revenue),
            "total_platform_fee": float(total_platform_fee),
            "total_refund_loss": float(total_refund_loss),
            "total_ad_cost": float(total_ad_cost),
            "total_fulfillment_cost": float(total_fulfillment_cost),
            "total_net_profit": float(total_net_profit),
            "overall_margin": float(overall_margin) if overall_margin else None,
        }

    async def get_platform_profitability(
        self,
        db: AsyncSession,
        platform: TargetPlatform,
        region: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get platform-level profitability snapshot.

        Args:
            db: Database session
            platform: Target platform
            region: Optional region filter
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Aggregated profitability snapshot
        """
        # Get all listings for this platform
        listing_stmt = select(PlatformListing.id).where(PlatformListing.platform == platform)

        if region:
            listing_stmt = listing_stmt.where(PlatformListing.region == region)

        listing_result = await db.execute(listing_stmt)
        listing_ids = [row[0] for row in listing_result.all()]

        if not listing_ids:
            return {
                "platform": platform.value,
                "region": region,
                "entry_count": 0,
                "total_gross_revenue": 0.0,
                "total_platform_fee": 0.0,
                "total_refund_loss": 0.0,
                "total_ad_cost": 0.0,
                "total_fulfillment_cost": 0.0,
                "total_net_profit": 0.0,
                "overall_margin": None,
            }

        # Build query for profit ledgers
        stmt = select(ProfitLedger).where(ProfitLedger.platform_listing_id.in_(listing_ids))

        if start_date:
            stmt = stmt.where(ProfitLedger.snapshot_date >= start_date)

        if end_date:
            stmt = stmt.where(ProfitLedger.snapshot_date <= end_date)

        result = await db.execute(stmt)
        ledgers = list(result.scalars().all())

        # Aggregate
        total_gross_revenue = sum((ledger.gross_revenue for ledger in ledgers), Decimal("0.00"))
        total_platform_fee = sum((ledger.platform_fee for ledger in ledgers), Decimal("0.00"))
        total_refund_loss = sum((ledger.refund_loss for ledger in ledgers), Decimal("0.00"))
        total_ad_cost = sum((ledger.ad_cost for ledger in ledgers), Decimal("0.00"))
        total_fulfillment_cost = sum((ledger.fulfillment_cost for ledger in ledgers), Decimal("0.00"))
        total_net_profit = sum((ledger.net_profit for ledger in ledgers), Decimal("0.00"))

        # Calculate overall margin
        overall_margin = None
        if total_gross_revenue > Decimal("0"):
            overall_margin = (total_net_profit / total_gross_revenue * 100).quantize(Decimal("0.01"))

        return {
            "platform": platform.value,
            "region": region,
            "entry_count": len(ledgers),
            "total_gross_revenue": float(total_gross_revenue),
            "total_platform_fee": float(total_platform_fee),
            "total_refund_loss": float(total_refund_loss),
            "total_ad_cost": float(total_ad_cost),
            "total_fulfillment_cost": float(total_fulfillment_cost),
            "total_net_profit": float(total_net_profit),
            "overall_margin": float(overall_margin) if overall_margin else None,
        }

    async def get_listing_profitability(
        self,
        db: AsyncSession,
        platform_listing_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get listing-level profitability snapshot.

        Args:
            db: Database session
            platform_listing_id: Listing ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Aggregated profitability snapshot
        """
        # Get listing
        listing = await db.get(PlatformListing, platform_listing_id)
        if not listing:
            raise ValueError(f"Listing {platform_listing_id} not found")

        # Build query for profit ledgers
        stmt = select(ProfitLedger).where(ProfitLedger.platform_listing_id == platform_listing_id)

        if start_date:
            stmt = stmt.where(ProfitLedger.snapshot_date >= start_date)

        if end_date:
            stmt = stmt.where(ProfitLedger.snapshot_date <= end_date)

        result = await db.execute(stmt)
        ledgers = list(result.scalars().all())

        # Aggregate
        total_gross_revenue = sum((ledger.gross_revenue for ledger in ledgers), Decimal("0.00"))
        total_platform_fee = sum((ledger.platform_fee for ledger in ledgers), Decimal("0.00"))
        total_refund_loss = sum((ledger.refund_loss for ledger in ledgers), Decimal("0.00"))
        total_ad_cost = sum((ledger.ad_cost for ledger in ledgers), Decimal("0.00"))
        total_fulfillment_cost = sum((ledger.fulfillment_cost for ledger in ledgers), Decimal("0.00"))
        total_net_profit = sum((ledger.net_profit for ledger in ledgers), Decimal("0.00"))

        # Calculate overall margin
        overall_margin = None
        if total_gross_revenue > Decimal("0"):
            overall_margin = (total_net_profit / total_gross_revenue * 100).quantize(Decimal("0.01"))

        return {
            "listing_id": str(platform_listing_id),
            "platform": listing.platform.value,
            "region": listing.region,
            "entry_count": len(ledgers),
            "total_gross_revenue": float(total_gross_revenue),
            "total_platform_fee": float(total_platform_fee),
            "total_refund_loss": float(total_refund_loss),
            "total_ad_cost": float(total_ad_cost),
            "total_fulfillment_cost": float(total_fulfillment_cost),
            "total_net_profit": float(total_net_profit),
            "overall_margin": float(overall_margin) if overall_margin else None,
        }

    async def get_profit_snapshot_in_currency(
        self,
        db: AsyncSession,
        *,
        target_currency: str,
        source_currency: str = "USD",
        product_variant_id: Optional[UUID] = None,
        listing_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict[str, Any]:
        """Get profit snapshot converted to target currency.

        Wraps get_profit_snapshot() and converts monetary fields when currencies differ.
        Falls back to original values if exchange rate is unavailable.
        """
        from app.services.currency_converter import CurrencyConverter

        snapshot = await self.get_profit_snapshot(
            db=db,
            product_variant_id=product_variant_id,
            listing_id=listing_id,
            start_date=start_date,
            end_date=end_date,
        )

        if source_currency == target_currency:
            converted_snapshot = snapshot.copy()
            converted_snapshot["currency"] = target_currency
            converted_snapshot["source_currency"] = source_currency
            converted_snapshot["conversion_applied"] = False
            return converted_snapshot

        currency_converter = CurrencyConverter()
        monetary_fields = [
            "total_gross_revenue",
            "total_platform_fee",
            "total_refund_loss",
            "total_ad_cost",
            "total_fulfillment_cost",
            "total_net_profit",
        ]

        converted_snapshot = snapshot.copy()
        try:
            for field in monetary_fields:
                if converted_snapshot.get(field) is not None:
                    converted_value = await currency_converter.convert_amount(
                        db=db,
                        amount=Decimal(str(converted_snapshot[field])),
                        from_currency=source_currency,
                        to_currency=target_currency,
                    )
                    converted_snapshot[field] = float(converted_value)
        except ValueError as e:
            self.logger.warning(
                "profit_snapshot_currency_conversion_failed",
                source_currency=source_currency,
                target_currency=target_currency,
                error=str(e),
            )

        converted_snapshot["currency"] = target_currency
        converted_snapshot["source_currency"] = source_currency
        converted_snapshot["conversion_applied"] = source_currency != target_currency
        return converted_snapshot

    async def get_regionalized_profit_snapshot(
        self,
        db: AsyncSession,
        *,
        platform: TargetPlatform,
        region: str,
        base_currency: str = "USD",
        local_currency: str = "USD",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict[str, Any]:
        """Get platform-region profit snapshot with tax and risk context.

        Args:
            db: Database session
            platform: Target platform
            region: Region code
            base_currency: Base currency for conversion (default: USD)
            local_currency: Local currency of the region (default: USD)
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Dict with platform-region profit snapshot, tax estimate, and risk notes
        """
        from app.services.currency_converter import CurrencyConverter
        from app.services.platform_policy_service import PlatformPolicyService

        # Get platform-region profitability (already filtered)
        snapshot = await self.get_platform_profitability(
            db=db,
            platform=platform,
            region=region,
            start_date=start_date,
            end_date=end_date,
        )

        # Convert monetary fields if currencies differ
        if local_currency != base_currency:
            currency_converter = CurrencyConverter()
            monetary_fields = [
                "total_gross_revenue",
                "total_platform_fee",
                "total_refund_loss",
                "total_ad_cost",
                "total_fulfillment_cost",
                "total_net_profit",
            ]

            converted_snapshot = {}
            try:
                for field in monetary_fields:
                    if snapshot.get(field) is not None:
                        converted_value = await currency_converter.convert_amount(
                            db=db,
                            amount=Decimal(str(snapshot[field])),
                            from_currency=local_currency,
                            to_currency=base_currency,
                        )
                        converted_snapshot[field] = float(converted_value)
            except ValueError as e:
                self.logger.warning(
                    "profit_snapshot_currency_conversion_failed",
                    platform=platform.value,
                    region=region,
                    source_currency=local_currency,
                    target_currency=base_currency,
                    error=str(e),
                )
                converted_snapshot = {field: snapshot.get(field) for field in monetary_fields}

            converted_snapshot["currency"] = base_currency
            converted_snapshot["source_currency"] = local_currency
            converted_snapshot["conversion_applied"] = True
        else:
            converted_snapshot = {
                field: snapshot.get(field)
                for field in [
                    "total_gross_revenue",
                    "total_platform_fee",
                    "total_refund_loss",
                    "total_ad_cost",
                    "total_fulfillment_cost",
                    "total_net_profit",
                ]
            }
            converted_snapshot["currency"] = base_currency
            converted_snapshot["source_currency"] = local_currency
            converted_snapshot["conversion_applied"] = False

        # Get tax and risk rules
        policy_service = PlatformPolicyService()
        tax_rules = await policy_service.get_tax_rules(
            db=db,
            platform=platform,
            region=region,
        )
        risk_rules = await policy_service.get_risk_rules(
            db=db,
            platform=platform,
            region=region,
        )

        # Calculate tax estimate
        tax_estimate = Decimal("0.00")
        gross_revenue = Decimal(str(snapshot.get("total_gross_revenue", 0)))
        for rule in tax_rules:
            tax_estimate += gross_revenue * rule.tax_rate

        return {
            **snapshot,
            "base_currency_snapshot": converted_snapshot,
            "tax_estimate": float(tax_estimate),
            "tax_rule_count": len(tax_rules),
            "risk_notes": [
                {
                    "rule_code": rule.rule_code,
                    "severity": rule.severity,
                    "rule_data": rule.rule_data,
                    "notes": rule.notes,
                }
                for rule in risk_rules
            ],
        }
