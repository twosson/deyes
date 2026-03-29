"""Order ingestion service for platform orders."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InventoryMode, OrderLineStatus, OrderStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import PlatformListing, PlatformOrder, PlatformOrderLine, ProductVariant
from app.services.inventory_allocator import InventoryAllocator

logger = get_logger(__name__)


class OrderIngestionService:
    """Service for ingesting customer orders from platforms."""

    def __init__(self):
        self.logger = get_logger(__name__)
        self.inventory_allocator = InventoryAllocator()

    async def ingest_order(
        self,
        db: AsyncSession,
        platform: TargetPlatform,
        region: str,
        platform_order_id: str,
        payload: dict,
    ) -> PlatformOrder:
        """Ingest an order with idempotency check.

        Idempotency key = f"order:{platform}:{platform_order_id}"

        Args:
            db: Database session
            platform: Target platform
            region: Region code
            platform_order_id: Platform's order ID
            payload: Order payload with order details

        Returns:
            PlatformOrder instance
        """
        # Check idempotency
        idempotency_key = f"order:{platform.value}:{platform_order_id}"
        stmt = select(PlatformOrder).where(PlatformOrder.idempotency_key == idempotency_key)
        result = await db.execute(stmt)
        existing_order = result.scalar_one_or_none()

        if existing_order:
            self.logger.info(
                "order_already_ingested",
                order_id=str(existing_order.id),
                platform=platform.value,
                platform_order_id=platform_order_id,
            )
            return existing_order

        # Create new order
        order = PlatformOrder(
            id=uuid4(),
            platform=platform,
            region=region,
            platform_order_id=platform_order_id,
            idempotency_key=idempotency_key,
            order_status=OrderStatus(payload.get("order_status", "pending")),
            currency=payload.get("currency", "USD"),
            buyer_country=payload.get("buyer_country"),
            total_amount=Decimal(str(payload.get("total_amount", "0.00"))),
            ordered_at=self._parse_datetime(payload.get("ordered_at")),
            paid_at=self._parse_datetime(payload.get("paid_at")),
            shipped_at=self._parse_datetime(payload.get("shipped_at")),
            delivered_at=self._parse_datetime(payload.get("delivered_at")),
        )

        db.add(order)
        await db.flush()

        # Ingest order lines
        for line_payload in payload.get("lines", []):
            await self.ingest_order_line(db, order.id, line_payload)

        await db.commit()
        await db.refresh(order, ["lines"])

        self.logger.info(
            "order_ingested",
            order_id=str(order.id),
            platform=platform.value,
            platform_order_id=platform_order_id,
            line_count=len(order.lines),
        )

        return order

    async def ingest_order_line(
        self,
        db: AsyncSession,
        order_id: UUID,
        line_payload: dict,
    ) -> PlatformOrderLine:
        """Ingest an order line with SKU/listing mapping.

        Args:
            db: Database session
            order_id: Parent order ID
            line_payload: Line item payload

        Returns:
            PlatformOrderLine instance
        """
        platform_sku = line_payload.get("platform_sku", "")

        # Try to map platform_sku to product_variant_id via PlatformListing
        platform_listing_id = None
        product_variant_id = None

        # Get order to determine platform
        order = await db.get(PlatformOrder, order_id)
        if order:
            # Try exact match first
            listing_stmt = select(PlatformListing).where(
                PlatformListing.platform == order.platform,
                PlatformListing.platform_listing_id == platform_sku,
            )
            listing_result = await db.execute(listing_stmt)
            listing = listing_result.scalar_one_or_none()

            if listing:
                platform_listing_id = listing.id
                product_variant_id = listing.product_variant_id

        # Create order line
        line = PlatformOrderLine(
            id=uuid4(),
            order_id=order_id,
            platform_listing_id=platform_listing_id,
            product_variant_id=product_variant_id,
            platform_sku=platform_sku,
            quantity=int(line_payload.get("quantity", 1)),
            unit_price=Decimal(str(line_payload.get("unit_price", "0.00"))),
            gross_revenue=Decimal(str(line_payload.get("gross_revenue", "0.00"))),
            discount_amount=Decimal(str(line_payload.get("discount_amount", "0.00"))),
            line_status=OrderLineStatus(line_payload.get("line_status", "pending")),
        )

        db.add(line)
        await db.flush()

        self.logger.info(
            "order_line_ingested",
            line_id=str(line.id),
            order_id=str(order_id),
            platform_sku=platform_sku,
            variant_mapped=product_variant_id is not None,
        )

        return line

    async def update_order_status(
        self,
        db: AsyncSession,
        order_id: UUID,
        new_status: OrderStatus,
    ) -> None:
        """Update order status.

        Args:
            db: Database session
            order_id: Order ID
            new_status: New order status
        """
        order = await db.get(PlatformOrder, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        order.order_status = new_status
        await db.commit()

        self.logger.info(
            "order_status_updated",
            order_id=str(order_id),
            new_status=new_status.value,
        )

    async def ingest_order_with_inventory(
        self,
        db: AsyncSession,
        platform: TargetPlatform,
        region: str,
        platform_order_id: str,
        payload: dict,
    ) -> tuple[PlatformOrder, dict]:
        """Ingest order and link inventory based on listing mode.

        For PRE_ORDER mode: create InventoryReservation.
        For STOCK_FIRST mode: record outbound inventory movement.

        Args:
            db: Database session
            platform: Target platform
            region: Region code
            platform_order_id: Platform's order ID
            payload: Order payload

        Returns:
            Tuple of (PlatformOrder, inventory_actions dict)
        """
        # 1. Ingest order
        order = await self.ingest_order(db, platform, region, platform_order_id, payload)

        inventory_actions = {
            "reservations_created": [],
            "outbound_movements": [],
            "skipped_lines": [],
        }

        # Refresh order to get lines
        await db.refresh(order, ["lines"])

        # 2. For each line, link inventory
        for line in order.lines:
            if not line.platform_listing_id or not line.product_variant_id:
                inventory_actions["skipped_lines"].append(
                    {
                        "line_id": str(line.id),
                        "reason": "missing_listing_or_variant_mapping",
                    }
                )
                continue

            listing = await db.get(PlatformListing, line.platform_listing_id)
            if not listing:
                inventory_actions["skipped_lines"].append(
                    {
                        "line_id": str(line.id),
                        "reason": "listing_not_found",
                    }
                )
                continue

            try:
                if listing.inventory_mode == InventoryMode.PRE_ORDER:
                    # Create reservation for pre-order
                    reservation = await self.inventory_allocator.reserve_inventory(
                        db=db,
                        variant_id=line.product_variant_id,
                        quantity=line.quantity,
                        reference_id=str(order.id),
                        reference_type="platform_order",
                        notes=f"Reserved for platform order {order.platform_order_id}",
                    )
                    inventory_actions["reservations_created"].append(
                        {
                            "line_id": str(line.id),
                            "reservation_id": str(reservation.id),
                            "quantity": line.quantity,
                        }
                    )
                else:  # STOCK_FIRST
                    # Direct outbound for stock-first
                    movement = await self.inventory_allocator.record_outbound(
                        db=db,
                        variant_id=line.product_variant_id,
                        quantity=line.quantity,
                        reference_id=str(order.id),
                    )
                    inventory_actions["outbound_movements"].append(
                        {
                            "line_id": str(line.id),
                            "movement_id": str(movement.movement_id),
                            "quantity": line.quantity,
                        }
                    )
            except ValueError as exc:
                inventory_actions["skipped_lines"].append(
                    {
                        "line_id": str(line.id),
                        "reason": str(exc),
                    }
                )

        self.logger.info(
            "order_inventory_linked",
            order_id=str(order.id),
            reservations_count=len(inventory_actions["reservations_created"]),
            outbound_count=len(inventory_actions["outbound_movements"]),
            skipped_count=len(inventory_actions["skipped_lines"]),
        )

        return order, inventory_actions

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse datetime string to datetime object."""
        if not value:
            return None

        try:
            # Try ISO format first
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            # Fall back to current time if parsing fails
            return datetime.now(timezone.utc)
