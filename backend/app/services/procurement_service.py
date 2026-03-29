"""Procurement service for purchase order management."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PurchaseOrderStatus
from app.core.logging import get_logger
from app.db.models import (
    ProductVariant,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierOffer,
)

logger = get_logger(__name__)


@dataclass
class CreatePOInput:
    """Input for creating a purchase order."""

    supplier_id: UUID
    items: list["POItemInput"]
    expected_delivery_date: Optional[datetime] = None
    notes: Optional[str] = None


@dataclass
class POItemInput:
    """Purchase order item input."""

    variant_id: UUID
    quantity: int


@dataclass
class POResult:
    """Purchase order creation result."""

    po_id: UUID
    po_number: str
    status: str
    total_amount: Decimal
    item_count: int


class ProcurementService:
    """Service for procurement operations."""

    def __init__(self):
        self.logger = get_logger(__name__)

    async def create_purchase_order(
        self,
        db: AsyncSession,
        input_data: CreatePOInput,
    ) -> POResult:
        """Create a new purchase order.

        Args:
            db: Database session
            input_data: PO creation input

        Returns:
            POResult with PO details
        """
        # Fetch supplier
        supplier_stmt = select(Supplier).where(Supplier.id == input_data.supplier_id)
        supplier_result = await db.execute(supplier_stmt)
        supplier = supplier_result.scalar_one_or_none()
        if not supplier:
            raise ValueError(f"Supplier {input_data.supplier_id} not found")

        # Validate and fetch variants with offers
        variant_ids = [item.variant_id for item in input_data.items]
        variants_stmt = select(ProductVariant).where(ProductVariant.id.in_(variant_ids))
        variants_result = await db.execute(variants_stmt)
        variants_map = {v.id: v for v in variants_result.scalars().all()}

        if len(variants_map) != len(variant_ids):
            raise ValueError("One or more variants not found")

        # Fetch supplier offers
        offers_stmt = select(SupplierOffer).where(
            and_(
                SupplierOffer.supplier_id == input_data.supplier_id,
                SupplierOffer.variant_id.in_(variant_ids),
            )
        )
        offers_result = await db.execute(offers_stmt)
        offers_map = {o.variant_id: o for o in offers_result.scalars().all()}

        # Generate PO number
        po_number = await self._generate_po_number(db)

        # Create PO
        po = PurchaseOrder(
            po_number=po_number,
            supplier_id=input_data.supplier_id,
            status=PurchaseOrderStatus.DRAFT,
            order_date=datetime.now(timezone.utc),
            expected_delivery_date=input_data.expected_delivery_date,
            notes=input_data.notes,
            currency="USD",
        )
        db.add(po)
        await db.flush()

        # Create PO items
        total_amount = Decimal("0")
        for item_input in input_data.items:
            offer = offers_map.get(item_input.variant_id)
            if not offer:
                raise ValueError(f"No offer from supplier for variant {item_input.variant_id}")

            line_total = offer.unit_price * item_input.quantity
            total_amount += line_total

            po_item = PurchaseOrderItem(
                purchase_order_id=po.id,
                variant_id=item_input.variant_id,
                quantity=item_input.quantity,
                unit_price=offer.unit_price,
                line_total=line_total,
            )
            db.add(po_item)

        po.total_amount = total_amount
        await db.commit()
        await db.refresh(po)

        self.logger.info(f"Created PO {po_number} with {len(input_data.items)} items")

        return POResult(
            po_id=po.id,
            po_number=po_number,
            status=po.status.value,
            total_amount=total_amount,
            item_count=len(input_data.items),
        )

    async def submit_purchase_order(
        self,
        db: AsyncSession,
        po_id: UUID,
    ) -> POResult:
        """Submit a purchase order to supplier.

        Args:
            db: Database session
            po_id: Purchase order ID

        Returns:
            Updated POResult
        """
        po_stmt = select(PurchaseOrder).where(PurchaseOrder.id == po_id)
        po_result = await db.execute(po_stmt)
        po = po_result.scalar_one_or_none()
        if not po:
            raise ValueError(f"PO {po_id} not found")

        if po.status != PurchaseOrderStatus.DRAFT:
            raise ValueError(f"Cannot submit PO in {po.status} status")

        po.status = PurchaseOrderStatus.SUBMITTED
        await db.commit()
        await db.refresh(po)

        self.logger.info(f"Submitted PO {po.po_number}")

        return POResult(
            po_id=po.id,
            po_number=po.po_number,
            status=po.status.value,
            total_amount=po.total_amount or Decimal("0"),
            item_count=len(po.items),
        )

    async def confirm_purchase_order(
        self,
        db: AsyncSession,
        po_id: UUID,
    ) -> POResult:
        """Confirm a purchase order (supplier accepted).

        Args:
            db: Database session
            po_id: Purchase order ID

        Returns:
            Updated POResult
        """
        po_stmt = select(PurchaseOrder).where(PurchaseOrder.id == po_id)
        po_result = await db.execute(po_stmt)
        po = po_result.scalar_one_or_none()
        if not po:
            raise ValueError(f"PO {po_id} not found")

        if po.status != PurchaseOrderStatus.SUBMITTED:
            raise ValueError(f"Cannot confirm PO in {po.status} status")

        po.status = PurchaseOrderStatus.CONFIRMED
        await db.commit()
        await db.refresh(po)

        self.logger.info(f"Confirmed PO {po.po_number}")

        return POResult(
            po_id=po.id,
            po_number=po.po_number,
            status=po.status.value,
            total_amount=po.total_amount or Decimal("0"),
            item_count=len(po.items),
        )

    async def _generate_po_number(self, db: AsyncSession) -> str:
        """Generate unique PO number."""
        # Simple sequential numbering: PO-YYYYMMDD-NNNNN
        from datetime import date

        today = date.today()
        prefix = f"PO-{today.strftime('%Y%m%d')}"

        # Count existing POs for today
        count_stmt = select(PurchaseOrder).where(PurchaseOrder.po_number.startswith(prefix))
        count_result = await db.execute(count_stmt)
        count = len(count_result.scalars().all())

        return f"{prefix}-{count + 1:05d}"
