"""Inventory allocation and movement service."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InboundShipmentStatus, InventoryMovementType, InventoryReservationStatus
from app.core.logging import get_logger
from app.db.models import (
    InboundShipment,
    InventoryLevel,
    InventoryMovement,
    InventoryReservation,
    ProductVariant,
)

logger = get_logger(__name__)


@dataclass
class InventoryAllocationResult:
    """Result of inventory allocation."""

    variant_id: UUID
    available_quantity: int
    reserved_quantity: int
    damaged_quantity: int


@dataclass
class InventoryMovementResult:
    """Result of inventory movement."""

    movement_id: UUID
    variant_id: UUID
    movement_type: str
    quantity: int
    new_available: int


class InventoryAllocator:
    """Service for inventory allocation and movement tracking."""

    def __init__(self):
        self.logger = get_logger(__name__)

    async def get_inventory_level(
        self,
        db: AsyncSession,
        variant_id: UUID,
    ) -> InventoryAllocationResult:
        """Get current inventory level for a variant.

        Args:
            db: Database session
            variant_id: Product variant ID

        Returns:
            InventoryAllocationResult with current levels
        """
        level_stmt = select(InventoryLevel).where(InventoryLevel.variant_id == variant_id)
        level_result = await db.execute(level_stmt)
        level = level_result.scalar_one_or_none()

        if not level:
            # Create default level if not exists
            level = InventoryLevel(
                variant_id=variant_id,
                available_quantity=0,
                reserved_quantity=0,
                damaged_quantity=0,
            )
            db.add(level)
            await db.commit()
            await db.refresh(level)

        return InventoryAllocationResult(
            variant_id=level.variant_id,
            available_quantity=level.available_quantity,
            reserved_quantity=level.reserved_quantity,
            damaged_quantity=level.damaged_quantity,
        )

    async def record_inbound(
        self,
        db: AsyncSession,
        variant_id: UUID,
        quantity: int,
        inbound_shipment_id: Optional[UUID] = None,
        reference_id: Optional[str] = None,
    ) -> InventoryMovementResult:
        """Record inbound inventory movement.

        Args:
            db: Database session
            variant_id: Product variant ID
            quantity: Quantity received
            inbound_shipment_id: Associated inbound shipment ID
            reference_id: Reference (PO number, shipment ID, etc.)

        Returns:
            InventoryMovementResult
        """
        # Verify variant exists
        variant_stmt = select(ProductVariant).where(ProductVariant.id == variant_id)
        variant_result = await db.execute(variant_stmt)
        if not variant_result.scalar_one_or_none():
            raise ValueError(f"Variant {variant_id} not found")

        # Get or create inventory level
        level_stmt = select(InventoryLevel).where(InventoryLevel.variant_id == variant_id)
        level_result = await db.execute(level_stmt)
        level = level_result.scalar_one_or_none()

        if not level:
            level = InventoryLevel(
                variant_id=variant_id,
                available_quantity=0,
                reserved_quantity=0,
                damaged_quantity=0,
            )
            db.add(level)
            await db.flush()

        # Update inventory
        level.available_quantity += quantity

        # Record movement
        movement = InventoryMovement(
            variant_id=variant_id,
            inbound_shipment_id=inbound_shipment_id,
            movement_type=InventoryMovementType.INBOUND,
            quantity=quantity,
            reference_id=reference_id,
            notes=f"Inbound received: {quantity} units",
        )
        db.add(movement)
        await db.commit()
        await db.refresh(level)

        self.logger.info(f"Recorded inbound: {quantity} units for variant {variant_id}")

        return InventoryMovementResult(
            movement_id=movement.id,
            variant_id=variant_id,
            movement_type=movement.movement_type.value,
            quantity=quantity,
            new_available=level.available_quantity,
        )

    async def record_outbound(
        self,
        db: AsyncSession,
        variant_id: UUID,
        quantity: int,
        reference_id: Optional[str] = None,
    ) -> InventoryMovementResult:
        """Record outbound inventory movement.

        Args:
            db: Database session
            variant_id: Product variant ID
            quantity: Quantity shipped
            reference_id: Reference (order ID, shipment ID, etc.)

        Returns:
            InventoryMovementResult
        """
        # Get inventory level
        level_stmt = select(InventoryLevel).where(InventoryLevel.variant_id == variant_id)
        level_result = await db.execute(level_stmt)
        level = level_result.scalar_one_or_none()

        if not level:
            raise ValueError(f"No inventory level for variant {variant_id}")

        if level.available_quantity < quantity:
            raise ValueError(
                f"Insufficient inventory: available={level.available_quantity}, requested={quantity}"
            )

        # Update inventory
        level.available_quantity -= quantity

        # Record movement
        movement = InventoryMovement(
            variant_id=variant_id,
            movement_type=InventoryMovementType.OUTBOUND,
            quantity=quantity,
            reference_id=reference_id,
            notes=f"Outbound shipped: {quantity} units",
        )
        db.add(movement)
        await db.commit()
        await db.refresh(level)

        self.logger.info(f"Recorded outbound: {quantity} units for variant {variant_id}")

        return InventoryMovementResult(
            movement_id=movement.id,
            variant_id=variant_id,
            movement_type=movement.movement_type.value,
            quantity=quantity,
            new_available=level.available_quantity,
        )

    async def record_adjustment(
        self,
        db: AsyncSession,
        variant_id: UUID,
        quantity_delta: int,
        reason: Optional[str] = None,
    ) -> InventoryMovementResult:
        """Record inventory adjustment (positive or negative).

        Args:
            db: Database session
            variant_id: Product variant ID
            quantity_delta: Quantity change (positive or negative)
            reason: Reason for adjustment

        Returns:
            InventoryMovementResult
        """
        # Get inventory level
        level_stmt = select(InventoryLevel).where(InventoryLevel.variant_id == variant_id)
        level_result = await db.execute(level_stmt)
        level = level_result.scalar_one_or_none()

        if not level:
            raise ValueError(f"No inventory level for variant {variant_id}")

        # Update inventory
        level.available_quantity += quantity_delta

        if level.available_quantity < 0:
            raise ValueError(f"Adjustment would result in negative inventory")

        # Record movement
        movement = InventoryMovement(
            variant_id=variant_id,
            movement_type=InventoryMovementType.ADJUSTMENT,
            quantity=abs(quantity_delta),
            reference_id=None,
            notes=f"Adjustment: {quantity_delta:+d} units. Reason: {reason or 'N/A'}",
        )
        db.add(movement)
        await db.commit()
        await db.refresh(level)

        self.logger.info(f"Recorded adjustment: {quantity_delta:+d} units for variant {variant_id}")

        return InventoryMovementResult(
            movement_id=movement.id,
            variant_id=variant_id,
            movement_type=movement.movement_type.value,
            quantity=abs(quantity_delta),
            new_available=level.available_quantity,
        )

    async def record_damage(
        self,
        db: AsyncSession,
        variant_id: UUID,
        quantity: int,
    ) -> InventoryMovementResult:
        """Record damaged inventory.

        Args:
            db: Database session
            variant_id: Product variant ID
            quantity: Quantity damaged

        Returns:
            InventoryMovementResult
        """
        # Get inventory level
        level_stmt = select(InventoryLevel).where(InventoryLevel.variant_id == variant_id)
        level_result = await db.execute(level_stmt)
        level = level_result.scalar_one_or_none()

        if not level:
            raise ValueError(f"No inventory level for variant {variant_id}")

        if level.available_quantity < quantity:
            raise ValueError(
                f"Insufficient inventory to mark as damaged: available={level.available_quantity}, requested={quantity}"
            )

        # Update inventory
        level.available_quantity -= quantity
        level.damaged_quantity += quantity

        # Record movement
        movement = InventoryMovement(
            variant_id=variant_id,
            movement_type=InventoryMovementType.ADJUSTMENT,
            quantity=quantity,
            reference_id=None,
            notes=f"Marked as damaged: {quantity} units",
        )
        db.add(movement)
        await db.commit()
        await db.refresh(level)

        self.logger.info(f"Recorded damage: {quantity} units for variant {variant_id}")

        return InventoryMovementResult(
            movement_id=movement.id,
            variant_id=variant_id,
            movement_type="damage",
            quantity=quantity,
            new_available=level.available_quantity,
        )

    async def receive_inbound_shipment(
        self,
        db: AsyncSession,
        inbound_shipment_id: UUID,
        received_items: dict[UUID, int],
    ) -> list[InventoryMovementResult]:
        """Receive an inbound shipment and update inventory.

        Args:
            db: Database session
            inbound_shipment_id: Inbound shipment ID
            received_items: Mapping of variant_id -> quantity received

        Returns:
            List of InventoryMovementResult for each item
        """
        # Verify shipment exists
        shipment_stmt = select(InboundShipment).where(InboundShipment.id == inbound_shipment_id)
        shipment_result = await db.execute(shipment_stmt)
        shipment = shipment_result.scalar_one_or_none()
        if not shipment:
            raise ValueError(f"Inbound shipment {inbound_shipment_id} not found")

        results = []
        for variant_id, quantity in received_items.items():
            result = await self.record_inbound(
                db,
                variant_id,
                quantity,
                inbound_shipment_id=inbound_shipment_id,
                reference_id=shipment.tracking_number,
            )
            results.append(result)

        # Update shipment status
        shipment.status = InboundShipmentStatus.RECEIVED
        shipment.actual_arrival_date = datetime.now(timezone.utc)
        await db.commit()

        self.logger.info(f"Received shipment {inbound_shipment_id} with {len(received_items)} items")

        return results

    async def reserve_inventory(
        self,
        db: AsyncSession,
        variant_id: UUID,
        quantity: int,
        reference_type: str,
        reference_id: str,
        notes: Optional[str] = None,
    ) -> InventoryReservation:
        """Reserve inventory for pre-order mode.

        Args:
            db: Database session
            variant_id: Product variant ID
            quantity: Quantity to reserve
            reference_type: Type of reference (e.g., "order", "listing")
            reference_id: Reference ID (e.g., order ID)
            notes: Optional notes

        Returns:
            Created InventoryReservation

        Raises:
            ValueError: If variant not found
        """
        # Verify variant exists
        variant_stmt = select(ProductVariant).where(ProductVariant.id == variant_id)
        variant_result = await db.execute(variant_stmt)
        if not variant_result.scalar_one_or_none():
            raise ValueError(f"Variant {variant_id} not found")

        # Get or create inventory level
        level_stmt = select(InventoryLevel).where(InventoryLevel.variant_id == variant_id)
        level_result = await db.execute(level_stmt)
        level = level_result.scalar_one_or_none()

        if not level:
            level = InventoryLevel(
                variant_id=variant_id,
                available_quantity=0,
                reserved_quantity=0,
                damaged_quantity=0,
            )
            db.add(level)
            await db.flush()

        # Update reserved quantity
        level.reserved_quantity += quantity

        # Create reservation
        reservation = InventoryReservation(
            id=uuid4(),
            variant_id=variant_id,
            quantity=quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            status=InventoryReservationStatus.ACTIVE,
            reserved_at=datetime.now(timezone.utc),
            notes=notes,
        )
        db.add(reservation)
        await db.commit()
        await db.refresh(reservation)

        self.logger.info(
            f"Reserved {quantity} units for variant {variant_id}, reference {reference_type}:{reference_id}"
        )

        return reservation

    async def fulfill_reservation(
        self,
        db: AsyncSession,
        reservation_id: UUID,
    ) -> InventoryMovementResult:
        """Fulfill a reservation by converting it to outbound movement.

        Args:
            db: Database session
            reservation_id: Reservation ID to fulfill

        Returns:
            InventoryMovementResult for the outbound movement

        Raises:
            ValueError: If reservation not found or already fulfilled/cancelled
        """
        # Get reservation
        reservation = await db.get(InventoryReservation, reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != InventoryReservationStatus.ACTIVE:
            raise ValueError(f"Reservation {reservation_id} is not active (status: {reservation.status})")

        # Get inventory level
        level_stmt = select(InventoryLevel).where(InventoryLevel.variant_id == reservation.variant_id)
        level_result = await db.execute(level_stmt)
        level = level_result.scalar_one_or_none()

        if not level:
            raise ValueError(f"No inventory level for variant {reservation.variant_id}")

        # Check sufficient inventory
        if level.available_quantity < reservation.quantity:
            raise ValueError(
                f"Insufficient inventory to fulfill reservation: "
                f"available={level.available_quantity}, reserved={reservation.quantity}"
            )

        # Update inventory: reduce available and reserved
        level.available_quantity -= reservation.quantity
        level.reserved_quantity -= reservation.quantity

        # Create outbound movement
        movement = InventoryMovement(
            variant_id=reservation.variant_id,
            movement_type=InventoryMovementType.OUTBOUND,
            quantity=reservation.quantity,
            reference_id=reservation.reference_id,
            notes=f"Fulfilled reservation {reservation_id}: {reservation.quantity} units",
        )
        db.add(movement)

        # Update reservation status
        reservation.status = InventoryReservationStatus.FULFILLED
        reservation.fulfilled_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(level)
        await db.refresh(movement)

        self.logger.info(
            f"Fulfilled reservation {reservation_id}: {reservation.quantity} units for variant {reservation.variant_id}"
        )

        return InventoryMovementResult(
            movement_id=movement.id,
            variant_id=reservation.variant_id,
            movement_type=movement.movement_type.value,
            quantity=reservation.quantity,
            new_available=level.available_quantity,
        )

    async def cancel_reservation(
        self,
        db: AsyncSession,
        reservation_id: UUID,
        reason: Optional[str] = None,
    ) -> None:
        """Cancel a reservation and release reserved quantity.

        Args:
            db: Database session
            reservation_id: Reservation ID to cancel
            reason: Optional cancellation reason

        Raises:
            ValueError: If reservation not found or already fulfilled/cancelled
        """
        # Get reservation
        reservation = await db.get(InventoryReservation, reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != InventoryReservationStatus.ACTIVE:
            raise ValueError(f"Reservation {reservation_id} is not active (status: {reservation.status})")

        # Get inventory level
        level_stmt = select(InventoryLevel).where(InventoryLevel.variant_id == reservation.variant_id)
        level_result = await db.execute(level_stmt)
        level = level_result.scalar_one_or_none()

        if not level:
            raise ValueError(f"No inventory level for variant {reservation.variant_id}")

        # Release reserved quantity
        level.reserved_quantity -= reservation.quantity

        # Update reservation status
        reservation.status = InventoryReservationStatus.CANCELLED
        reservation.cancelled_at = datetime.now(timezone.utc)
        if reason:
            reservation.notes = f"{reservation.notes or ''}\nCancelled: {reason}".strip()

        await db.commit()

        self.logger.info(
            f"Cancelled reservation {reservation_id}: released {reservation.quantity} units for variant {reservation.variant_id}"
        )
