"""Tests for profit ledger service extensions."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InventoryMode, OrderLineStatus, OrderStatus, TargetPlatform
from app.db.models import (
    PlatformListing,
    PlatformOrder,
    PlatformOrderLine,
    ProductMaster,
    ProductVariant,
    Supplier,
    SupplierOffer,
)
from app.services.order_ingestion_service import OrderIngestionService
from app.services.profit_ledger_service import ProfitLedgerService


@pytest_asyncio.fixture
async def sample_supplier_with_variants(db_session: AsyncSession):
    """Create a sample supplier with multiple variants."""
    supplier = Supplier(
        id=uuid4(),
        name="Test Profit Supplier",
        status="active",
    )
    db_session.add(supplier)
    await db_session.flush()

    variants = []
    for i in range(3):
        master = ProductMaster(
            id=uuid4(),
            internal_sku=f"TEST-PROFIT-SKU-{i:03d}",
            name=f"Test Profit Product {i}",
            status="active",
        )
        db_session.add(master)
        await db_session.flush()

        variant = ProductVariant(
            id=uuid4(),
            master_id=master.id,
            variant_sku=f"TEST-PROFIT-SKU-{i:03d}-V1",
            inventory_mode=InventoryMode.STOCK_FIRST,
            status="active",
        )
        db_session.add(variant)
        await db_session.flush()

        offer = SupplierOffer(
            id=uuid4(),
            supplier_id=supplier.id,
            variant_id=variant.id,
            unit_price=Decimal("10.00"),
            currency="USD",
            moq=100,
            lead_time_days=30,
        )
        db_session.add(offer)

        variants.append(variant)

    await db_session.commit()

    return {"supplier": supplier, "variants": variants}


@pytest.mark.asyncio
async def test_allocate_ad_cost(db_session: AsyncSession):
    """Test ad cost allocation to profit ledger entries."""
    # Create variant and listing
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-AD-SKU-001",
        name="Test Ad Product",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-AD-SKU-001-V1",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status="active",
    )
    db_session.add(variant)
    await db_session.flush()

    supplier = Supplier(
        id=uuid4(),
        name="Test Ad Supplier",
        status="active",
    )
    db_session.add(supplier)
    await db_session.flush()

    offer = SupplierOffer(
        id=uuid4(),
        supplier_id=supplier.id,
        variant_id=variant.id,
        unit_price=Decimal("10.00"),
        currency="USD",
        moq=100,
        lead_time_days=30,
    )
    db_session.add(offer)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=uuid4(),
        product_variant_id=variant.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_listing_id="AMZN-AD-001",
        price=Decimal("30.00"),
        currency="USD",
        inventory=100,
        status="active",
    )
    db_session.add(listing)
    await db_session.commit()

    # Create orders and profit ledgers
    order_service = OrderIngestionService()
    profit_service = ProfitLedgerService()

    for i in range(2):
        payload = {
            "order_status": "confirmed",
            "currency": "USD",
            "total_amount": "30.00",
            "ordered_at": "2026-03-29T12:00:00Z",
            "lines": [
                {
                    "platform_sku": "AMZN-AD-001",
                    "quantity": 1,
                    "unit_price": "30.00",
                    "gross_revenue": "30.00",
                    "line_status": "confirmed",
                }
            ],
        }

        order = await order_service.ingest_order(
            db=db_session,
            platform=TargetPlatform.AMAZON,
            region="us",
            platform_order_id=f"ORDER-AD-{i:03d}",
            payload=payload,
        )

        await profit_service.build_order_profit_ledger(
            db=db_session,
            order_line_id=order.lines[0].id,
        )

    # Allocate ad cost
    updated_ledgers = await profit_service.allocate_ad_cost(
        db=db_session,
        platform_listing_id=listing.id,
        ad_cost=Decimal("10.00"),
        allocation_date=date.today(),
    )

    assert len(updated_ledgers) == 2
    # Each ledger should get 5.00 ad cost (proportional to 30.00 revenue each)
    for ledger in updated_ledgers:
        assert ledger.ad_cost == Decimal("5.00")


@pytest.mark.asyncio
async def test_get_supplier_profitability(db_session: AsyncSession, sample_supplier_with_variants):
    """Test supplier-level profitability snapshot."""
    # Create orders for each variant
    order_service = OrderIngestionService()
    profit_service = ProfitLedgerService()

    for i, variant in enumerate(sample_supplier_with_variants["variants"]):
        listing = PlatformListing(
            id=uuid4(),
            candidate_product_id=uuid4(),
            product_variant_id=variant.id,
            inventory_mode=InventoryMode.STOCK_FIRST,
            platform=TargetPlatform.AMAZON,
            region="us",
            platform_listing_id=f"AMZN-SUPPLIER-{i:03d}",
            price=Decimal("30.00"),
            currency="USD",
            inventory=100,
            status="active",
        )
        db_session.add(listing)
        await db_session.flush()

        payload = {
            "order_status": "confirmed",
            "currency": "USD",
            "total_amount": "30.00",
            "ordered_at": "2026-03-29T12:00:00Z",
            "lines": [
                {
                    "platform_sku": f"AMZN-SUPPLIER-{i:03d}",
                    "quantity": 1,
                    "unit_price": "30.00",
                    "gross_revenue": "30.00",
                    "line_status": "confirmed",
                }
            ],
        }

        order = await order_service.ingest_order(
            db=db_session,
            platform=TargetPlatform.AMAZON,
            region="us",
            platform_order_id=f"ORDER-SUPPLIER-{i:03d}",
            payload=payload,
        )

        await profit_service.build_order_profit_ledger(
            db=db_session,
            order_line_id=order.lines[0].id,
        )

    # Get supplier profitability
    snapshot = await profit_service.get_supplier_profitability(
        db=db_session,
        supplier_id=sample_supplier_with_variants["supplier"].id,
    )

    assert snapshot["entry_count"] == 3
    assert snapshot["total_gross_revenue"] == 90.0  # 30.00 * 3
    assert snapshot["supplier_name"] == "Test Profit Supplier"


@pytest.mark.asyncio
async def test_get_platform_profitability(db_session: AsyncSession):
    """Test platform-level profitability snapshot."""
    # Create variant and listing
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-PLATFORM-SKU-001",
        name="Test Platform Product",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-PLATFORM-SKU-001-V1",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status="active",
    )
    db_session.add(variant)
    await db_session.flush()

    supplier = Supplier(
        id=uuid4(),
        name="Test Platform Supplier",
        status="active",
    )
    db_session.add(supplier)
    await db_session.flush()

    offer = SupplierOffer(
        id=uuid4(),
        supplier_id=supplier.id,
        variant_id=variant.id,
        unit_price=Decimal("10.00"),
        currency="USD",
        moq=100,
        lead_time_days=30,
    )
    db_session.add(offer)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=uuid4(),
        product_variant_id=variant.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.TEMU,
        region="us",
        platform_listing_id="TEMU-PLATFORM-001",
        price=Decimal("25.00"),
        currency="USD",
        inventory=100,
        status="active",
    )
    db_session.add(listing)
    await db_session.commit()

    # Create orders
    order_service = OrderIngestionService()
    profit_service = ProfitLedgerService()

    for i in range(2):
        payload = {
            "order_status": "confirmed",
            "currency": "USD",
            "total_amount": "25.00",
            "ordered_at": "2026-03-29T12:00:00Z",
            "lines": [
                {
                    "platform_sku": "TEMU-PLATFORM-001",
                    "quantity": 1,
                    "unit_price": "25.00",
                    "gross_revenue": "25.00",
                    "line_status": "confirmed",
                }
            ],
        }

        order = await order_service.ingest_order(
            db=db_session,
            platform=TargetPlatform.TEMU,
            region="us",
            platform_order_id=f"ORDER-PLATFORM-{i:03d}",
            payload=payload,
        )

        await profit_service.build_order_profit_ledger(
            db=db_session,
            order_line_id=order.lines[0].id,
        )

    # Get platform profitability
    snapshot = await profit_service.get_platform_profitability(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
    )

    assert snapshot["entry_count"] == 2
    assert snapshot["total_gross_revenue"] == 50.0  # 25.00 * 2
    assert snapshot["platform"] == "temu"
    assert snapshot["region"] == "us"


@pytest.mark.asyncio
async def test_get_listing_profitability(db_session: AsyncSession):
    """Test listing-level profitability snapshot."""
    # Create variant and listing
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-LISTING-SKU-001",
        name="Test Listing Product",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-LISTING-SKU-001-V1",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status="active",
    )
    db_session.add(variant)
    await db_session.flush()

    supplier = Supplier(
        id=uuid4(),
        name="Test Listing Supplier",
        status="active",
    )
    db_session.add(supplier)
    await db_session.flush()

    offer = SupplierOffer(
        id=uuid4(),
        supplier_id=supplier.id,
        variant_id=variant.id,
        unit_price=Decimal("10.00"),
        currency="USD",
        moq=100,
        lead_time_days=30,
    )
    db_session.add(offer)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=uuid4(),
        product_variant_id=variant.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_listing_id="AMZN-LISTING-001",
        price=Decimal("30.00"),
        currency="USD",
        inventory=100,
        status="active",
    )
    db_session.add(listing)
    await db_session.commit()

    # Create orders
    order_service = OrderIngestionService()
    profit_service = ProfitLedgerService()

    for i in range(3):
        payload = {
            "order_status": "confirmed",
            "currency": "USD",
            "total_amount": "30.00",
            "ordered_at": "2026-03-29T12:00:00Z",
            "lines": [
                {
                    "platform_sku": "AMZN-LISTING-001",
                    "quantity": 1,
                    "unit_price": "30.00",
                    "gross_revenue": "30.00",
                    "line_status": "confirmed",
                }
            ],
        }

        order = await order_service.ingest_order(
            db=db_session,
            platform=TargetPlatform.AMAZON,
            region="us",
            platform_order_id=f"ORDER-LISTING-{i:03d}",
            payload=payload,
        )

        await profit_service.build_order_profit_ledger(
            db=db_session,
            order_line_id=order.lines[0].id,
        )

    # Get listing profitability
    snapshot = await profit_service.get_listing_profitability(
        db=db_session,
        platform_listing_id=listing.id,
    )

    assert snapshot["entry_count"] == 3
    assert snapshot["total_gross_revenue"] == 90.0  # 30.00 * 3
    assert snapshot["platform"] == "amazon"
    assert snapshot["region"] == "us"
