"""Tests for inventory allocator service."""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    InventoryMode,
    InventoryMovementType,
    ProductMasterStatus,
    ProductVariantStatus,
)
from app.db.models import (
    InboundShipment,
    ProductMaster,
    ProductVariant,
)
from app.services.inventory_allocator import InventoryAllocator


@pytest_asyncio.fixture
async def sample_product_variant(db_session):
    """Create a sample product variant."""
    master = ProductMaster(
        id=uuid4(),
        internal_sku="SKU-001",
        name="Test Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-001-RED-M",
        attributes={"color": "red", "size": "M"},
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(variant)
    return variant


@pytest.mark.asyncio
async def test_get_inventory_level_creates_default(db_session, sample_product_variant):
    """Test getting inventory level creates default if not exists."""
    allocator = InventoryAllocator()

    result = await allocator.get_inventory_level(db_session, sample_product_variant.id)

    assert result.variant_id == sample_product_variant.id
    assert result.available_quantity == 0
    assert result.reserved_quantity == 0
    assert result.damaged_quantity == 0


@pytest.mark.asyncio
async def test_record_inbound(db_session, sample_product_variant):
    """Test recording inbound inventory."""
    allocator = InventoryAllocator()

    result = await allocator.record_inbound(
        db_session,
        sample_product_variant.id,
        quantity=100,
        reference_id="PO-20260329-00001",
    )

    assert result.variant_id == sample_product_variant.id
    assert result.quantity == 100
    assert result.new_available == 100
    assert result.movement_type == InventoryMovementType.INBOUND.value


@pytest.mark.asyncio
async def test_record_outbound(db_session, sample_product_variant):
    """Test recording outbound inventory."""
    allocator = InventoryAllocator()

    # First add inventory
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=100)

    # Then remove some
    result = await allocator.record_outbound(
        db_session,
        sample_product_variant.id,
        quantity=30,
        reference_id="ORDER-001",
    )

    assert result.quantity == 30
    assert result.new_available == 70
    assert result.movement_type == InventoryMovementType.OUTBOUND.value


@pytest.mark.asyncio
async def test_record_outbound_insufficient_inventory(db_session, sample_product_variant):
    """Test outbound fails with insufficient inventory."""
    allocator = InventoryAllocator()

    # Add only 50 units
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=50)

    # Try to remove 100
    with pytest.raises(ValueError, match="Insufficient inventory"):
        await allocator.record_outbound(db_session, sample_product_variant.id, quantity=100)


@pytest.mark.asyncio
async def test_record_adjustment_positive(db_session, sample_product_variant):
    """Test positive inventory adjustment."""
    allocator = InventoryAllocator()

    # Add initial inventory
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=100)

    # Adjust up
    result = await allocator.record_adjustment(
        db_session,
        sample_product_variant.id,
        quantity_delta=50,
        reason="Recount correction",
    )

    assert result.new_available == 150
    assert result.movement_type == InventoryMovementType.ADJUSTMENT.value


@pytest.mark.asyncio
async def test_record_adjustment_negative(db_session, sample_product_variant):
    """Test negative inventory adjustment."""
    allocator = InventoryAllocator()

    # Add initial inventory
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=100)

    # Adjust down
    result = await allocator.record_adjustment(
        db_session,
        sample_product_variant.id,
        quantity_delta=-30,
        reason="Shrinkage",
    )

    assert result.new_available == 70


@pytest.mark.asyncio
async def test_record_adjustment_negative_insufficient(db_session, sample_product_variant):
    """Test negative adjustment fails if would go negative."""
    allocator = InventoryAllocator()

    # Add only 50 units
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=50)

    # Try to adjust by -100
    with pytest.raises(ValueError, match="negative inventory"):
        await allocator.record_adjustment(db_session, sample_product_variant.id, quantity_delta=-100)


@pytest.mark.asyncio
async def test_record_damage(db_session, sample_product_variant):
    """Test recording damaged inventory."""
    allocator = InventoryAllocator()

    # Add inventory
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=100)

    # Mark some as damaged
    result = await allocator.record_damage(db_session, sample_product_variant.id, quantity=10)

    assert result.new_available == 90

    # Check inventory level
    level_result = await allocator.get_inventory_level(db_session, sample_product_variant.id)
    assert level_result.available_quantity == 90
    assert level_result.damaged_quantity == 10


@pytest.mark.asyncio
async def test_record_damage_insufficient(db_session, sample_product_variant):
    """Test damage recording fails with insufficient inventory."""
    allocator = InventoryAllocator()

    # Add only 50 units
    await allocator.record_inbound(db_session, sample_product_variant.id, quantity=50)

    # Try to mark 100 as damaged
    with pytest.raises(ValueError, match="Insufficient inventory to mark as damaged"):
        await allocator.record_damage(db_session, sample_product_variant.id, quantity=100)


@pytest.mark.asyncio
async def test_receive_inbound_shipment(db_session, sample_product_variant):
    """Test receiving an inbound shipment."""
    from app.core.enums import InboundShipmentStatus, PurchaseOrderStatus
    from app.db.models import PurchaseOrder, Supplier

    allocator = InventoryAllocator()

    # Create supplier and PO
    supplier = Supplier(
        id=uuid4(),
        name="Test Supplier",
        status="active",
    )
    db_session.add(supplier)
    await db_session.flush()

    po = PurchaseOrder(
        id=uuid4(),
        po_number="PO-20260329-00001",
        supplier_id=supplier.id,
        status=PurchaseOrderStatus.CONFIRMED,
    )
    db_session.add(po)
    await db_session.flush()

    shipment = InboundShipment(
        id=uuid4(),
        purchase_order_id=po.id,
        tracking_number="TRACK-001",
        status=InboundShipmentStatus.IN_TRANSIT,
    )
    db_session.add(shipment)
    await db_session.commit()

    # Receive shipment
    results = await allocator.receive_inbound_shipment(
        db_session,
        shipment.id,
        {sample_product_variant.id: 100},
    )

    assert len(results) == 1
    assert results[0].new_available == 100

    # Verify shipment status updated
    await db_session.refresh(shipment)
    assert shipment.status == "received"
