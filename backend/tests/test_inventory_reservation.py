"""Tests for inventory reservation functionality."""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    InventoryMode,
    InventoryReservationStatus,
    ProductMasterStatus,
    ProductVariantStatus,
)
from app.db.models import (
    ProductMaster,
    ProductVariant,
)
from app.services.inventory_allocator import InventoryAllocator


@pytest_asyncio.fixture
async def sample_product_variant(db_session):
    """Create a sample product variant."""
    master = ProductMaster(
        id=uuid4(),
        internal_sku="SKU-RESERVE-001",
        name="Test Product for Reservation",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-RESERVE-001-RED-M",
        attributes={"color": "red", "size": "M"},
        inventory_mode=InventoryMode.PRE_ORDER,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(variant)
    return variant


@pytest.mark.asyncio
async def test_reserve_inventory_creates_reservation(db_session, sample_product_variant):
    """Test creating an inventory reservation."""
    allocator = InventoryAllocator()

    reservation = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=10,
        reference_type="order",
        reference_id="ORDER-001",
        notes="Test reservation",
    )

    assert reservation.variant_id == sample_product_variant.id
    assert reservation.quantity == 10
    assert reservation.reference_type == "order"
    assert reservation.reference_id == "ORDER-001"
    assert reservation.status == InventoryReservationStatus.ACTIVE
    assert reservation.reserved_at is not None
    assert reservation.fulfilled_at is None
    assert reservation.cancelled_at is None

    # Check inventory level updated
    level = await allocator.get_inventory_level(db_session, sample_product_variant.id)
    assert level.reserved_quantity == 10


@pytest.mark.asyncio
async def test_reserve_inventory_accumulates_reserved_quantity(db_session, sample_product_variant):
    """Test multiple reservations accumulate reserved quantity."""
    allocator = InventoryAllocator()

    await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=10,
        reference_type="order",
        reference_id="ORDER-001",
    )

    await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=5,
        reference_type="order",
        reference_id="ORDER-002",
    )

    level = await allocator.get_inventory_level(db_session, sample_product_variant.id)
    assert level.reserved_quantity == 15


@pytest.mark.asyncio
async def test_fulfill_reservation_creates_outbound_movement(db_session, sample_product_variant):
    """Test fulfilling a reservation creates outbound movement."""
    allocator = InventoryAllocator()

    # Add inventory
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=100)

    # Create reservation
    reservation = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=10,
        reference_type="order",
        reference_id="ORDER-001",
    )

    # Fulfill reservation
    result = await allocator.fulfill_reservation(db_session, reservation.id)

    assert result.variant_id == sample_product_variant.id
    assert result.quantity == 10
    assert result.movement_type == "outbound"
    assert result.new_available == 90

    # Check reservation status
    await db_session.refresh(reservation)
    assert reservation.status == InventoryReservationStatus.FULFILLED
    assert reservation.fulfilled_at is not None

    # Check inventory level
    level = await allocator.get_inventory_level(db_session, sample_product_variant.id)
    assert level.available_quantity == 90
    assert level.reserved_quantity == 0


@pytest.mark.asyncio
async def test_fulfill_reservation_fails_with_insufficient_inventory(db_session, sample_product_variant):
    """Test fulfilling reservation fails if insufficient inventory."""
    allocator = InventoryAllocator()

    # Add only 5 units
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=5)

    # Reserve 10 units
    reservation = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=10,
        reference_type="order",
        reference_id="ORDER-001",
    )

    # Try to fulfill - should fail
    with pytest.raises(ValueError, match="Insufficient inventory"):
        await allocator.fulfill_reservation(db_session, reservation.id)


@pytest.mark.asyncio
async def test_fulfill_reservation_fails_if_already_fulfilled(db_session, sample_product_variant):
    """Test fulfilling reservation fails if already fulfilled."""
    allocator = InventoryAllocator()

    # Add inventory
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=100)

    # Create and fulfill reservation
    reservation = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=10,
        reference_type="order",
        reference_id="ORDER-001",
    )
    await allocator.fulfill_reservation(db_session, reservation.id)

    # Try to fulfill again - should fail
    with pytest.raises(ValueError, match="is not active"):
        await allocator.fulfill_reservation(db_session, reservation.id)


@pytest.mark.asyncio
async def test_cancel_reservation_releases_reserved_quantity(db_session, sample_product_variant):
    """Test cancelling a reservation releases reserved quantity."""
    allocator = InventoryAllocator()

    # Create reservation
    reservation = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=10,
        reference_type="order",
        reference_id="ORDER-001",
    )

    # Cancel reservation
    await allocator.cancel_reservation(db_session, reservation.id, reason="Customer cancelled")

    # Check reservation status
    await db_session.refresh(reservation)
    assert reservation.status == InventoryReservationStatus.CANCELLED
    assert reservation.cancelled_at is not None
    assert "Customer cancelled" in reservation.notes

    # Check inventory level
    level = await allocator.get_inventory_level(db_session, sample_product_variant.id)
    assert level.reserved_quantity == 0


@pytest.mark.asyncio
async def test_cancel_reservation_fails_if_already_cancelled(db_session, sample_product_variant):
    """Test cancelling reservation fails if already cancelled."""
    allocator = InventoryAllocator()

    # Create and cancel reservation
    reservation = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=10,
        reference_type="order",
        reference_id="ORDER-001",
    )
    await allocator.cancel_reservation(db_session, reservation.id)

    # Try to cancel again - should fail
    with pytest.raises(ValueError, match="is not active"):
        await allocator.cancel_reservation(db_session, reservation.id)


@pytest.mark.asyncio
async def test_cancel_reservation_fails_if_already_fulfilled(db_session, sample_product_variant):
    """Test cancelling reservation fails if already fulfilled."""
    allocator = InventoryAllocator()

    # Add inventory
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=100)

    # Create and fulfill reservation
    reservation = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=10,
        reference_type="order",
        reference_id="ORDER-001",
    )
    await allocator.fulfill_reservation(db_session, reservation.id)

    # Try to cancel - should fail
    with pytest.raises(ValueError, match="is not active"):
        await allocator.cancel_reservation(db_session, reservation.id)


@pytest.mark.asyncio
async def test_multiple_reservations_lifecycle(db_session, sample_product_variant):
    """Test complete lifecycle with multiple reservations."""
    allocator = InventoryAllocator()

    # Add inventory
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=100)

    # Create multiple reservations
    res1 = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=10,
        reference_type="order",
        reference_id="ORDER-001",
    )

    res2 = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=20,
        reference_type="order",
        reference_id="ORDER-002",
    )

    res3 = await allocator.reserve_inventory(
        db_session,
        sample_product_variant.id,
        quantity=15,
        reference_type="order",
        reference_id="ORDER-003",
    )

    # Check reserved quantity
    level = await allocator.get_inventory_level(db_session, sample_product_variant.id)
    assert level.reserved_quantity == 45
    assert level.available_quantity == 100

    # Fulfill first reservation
    await allocator.fulfill_reservation(db_session, res1.id)
    level = await allocator.get_inventory_level(db_session, sample_product_variant.id)
    assert level.reserved_quantity == 35
    assert level.available_quantity == 90

    # Cancel second reservation
    await allocator.cancel_reservation(db_session, res2.id)
    level = await allocator.get_inventory_level(db_session, sample_product_variant.id)
    assert level.reserved_quantity == 15
    assert level.available_quantity == 90

    # Fulfill third reservation
    await allocator.fulfill_reservation(db_session, res3.id)
    level = await allocator.get_inventory_level(db_session, sample_product_variant.id)
    assert level.reserved_quantity == 0
    assert level.available_quantity == 75
