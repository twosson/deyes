"""Tests for procurement service."""
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    InventoryMode,
    ProductMasterStatus,
    ProductVariantStatus,
    PurchaseOrderStatus,
    SupplierStatus,
)
from app.db.models import (
    ProductMaster,
    ProductVariant,
    Supplier,
    SupplierOffer,
)
from app.services.procurement_service import CreatePOInput, POItemInput, ProcurementService


@pytest_asyncio.fixture
async def sample_product_master(db_session):
    """Create a sample product master."""
    master = ProductMaster(
        id=uuid4(),
        internal_sku="SKU-001",
        name="Test Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.commit()
    await db_session.refresh(master)
    return master


@pytest_asyncio.fixture
async def sample_product_variant(db_session, sample_product_master):
    """Create a sample product variant."""
    variant = ProductVariant(
        id=uuid4(),
        master_id=sample_product_master.id,
        variant_sku="SKU-001-RED-M",
        attributes={"color": "red", "size": "M"},
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(variant)
    return variant


@pytest_asyncio.fixture
async def sample_supplier(db_session):
    """Create a sample supplier."""
    supplier = Supplier(
        id=uuid4(),
        name="Test Supplier",
        alibaba_id="1234567890",
        contact_email="supplier@example.com",
        status=SupplierStatus.ACTIVE,
    )
    db_session.add(supplier)
    await db_session.commit()
    await db_session.refresh(supplier)
    return supplier


@pytest_asyncio.fixture
async def sample_supplier_offer(db_session, sample_supplier, sample_product_variant):
    """Create a sample supplier offer."""
    offer = SupplierOffer(
        id=uuid4(),
        supplier_id=sample_supplier.id,
        variant_id=sample_product_variant.id,
        unit_price=Decimal("10.00"),
        currency="USD",
        moq=100,
        lead_time_days=30,
    )
    db_session.add(offer)
    await db_session.commit()
    await db_session.refresh(offer)
    return offer


@pytest.mark.asyncio
async def test_create_purchase_order(db_session, sample_supplier, sample_product_variant, sample_supplier_offer):
    """Test creating a purchase order."""
    service = ProcurementService()

    input_data = CreatePOInput(
        supplier_id=sample_supplier.id,
        items=[
            POItemInput(variant_id=sample_product_variant.id, quantity=100),
        ],
        notes="Test PO",
    )

    result = await service.create_purchase_order(db_session, input_data)

    assert result.po_id is not None
    assert result.po_number.startswith("PO-")
    assert result.status == PurchaseOrderStatus.DRAFT.value
    assert result.total_amount == Decimal("1000.00")  # 100 * 10.00
    assert result.item_count == 1


@pytest.mark.asyncio
async def test_submit_purchase_order(db_session, sample_supplier, sample_product_variant, sample_supplier_offer):
    """Test submitting a purchase order."""
    service = ProcurementService()

    # Create PO
    input_data = CreatePOInput(
        supplier_id=sample_supplier.id,
        items=[POItemInput(variant_id=sample_product_variant.id, quantity=100)],
    )
    create_result = await service.create_purchase_order(db_session, input_data)

    # Submit PO
    submit_result = await service.submit_purchase_order(db_session, create_result.po_id)

    assert submit_result.status == PurchaseOrderStatus.SUBMITTED.value


@pytest.mark.asyncio
async def test_confirm_purchase_order(db_session, sample_supplier, sample_product_variant, sample_supplier_offer):
    """Test confirming a purchase order."""
    service = ProcurementService()

    # Create and submit PO
    input_data = CreatePOInput(
        supplier_id=sample_supplier.id,
        items=[POItemInput(variant_id=sample_product_variant.id, quantity=100)],
    )
    create_result = await service.create_purchase_order(db_session, input_data)
    await service.submit_purchase_order(db_session, create_result.po_id)

    # Confirm PO
    confirm_result = await service.confirm_purchase_order(db_session, create_result.po_id)

    assert confirm_result.status == PurchaseOrderStatus.CONFIRMED.value


@pytest.mark.asyncio
async def test_create_po_with_missing_supplier(db_session):
    """Test creating PO with non-existent supplier."""
    service = ProcurementService()

    input_data = CreatePOInput(
        supplier_id=uuid4(),
        items=[],
    )

    with pytest.raises(ValueError, match="Supplier .* not found"):
        await service.create_purchase_order(db_session, input_data)


@pytest.mark.asyncio
async def test_create_po_with_missing_variant(db_session, sample_supplier):
    """Test creating PO with non-existent variant."""
    service = ProcurementService()

    input_data = CreatePOInput(
        supplier_id=sample_supplier.id,
        items=[POItemInput(variant_id=uuid4(), quantity=100)],
    )

    with pytest.raises(ValueError, match="One or more variants not found"):
        await service.create_purchase_order(db_session, input_data)


@pytest.mark.asyncio
async def test_create_po_with_missing_offer(db_session, sample_supplier, sample_product_variant):
    """Test creating PO when supplier has no offer for variant."""
    service = ProcurementService()

    input_data = CreatePOInput(
        supplier_id=sample_supplier.id,
        items=[POItemInput(variant_id=sample_product_variant.id, quantity=100)],
    )

    with pytest.raises(ValueError, match="No offer from supplier"):
        await service.create_purchase_order(db_session, input_data)
