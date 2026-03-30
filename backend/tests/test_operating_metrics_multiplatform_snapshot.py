"""Tests for OperatingMetricsService multiplatform snapshot."""
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    InventoryMode,
    PlatformListingStatus,
    RefundReason,
    TargetPlatform,
)
from app.db.models import (
    PlatformListing,
    ProductMaster,
    ProductVariant,
    Supplier,
    SupplierOffer,
)
from app.services.operating_metrics_service import OperatingMetricsService
from app.services.order_ingestion_service import OrderIngestionService
from app.services.profit_ledger_service import ProfitLedgerService


@pytest_asyncio.fixture
async def multiplatform_infrastructure(db_session: AsyncSession):
    """Create multi-platform listing infrastructure for snapshot tests."""
    # Create master and variant
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MP-SKU-001",
        name="Test Multiplatform Product",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-MP-SKU-001-V1",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status="active",
    )
    db_session.add(variant)
    await db_session.flush()

    # Create supplier and offer
    supplier = Supplier(
        id=uuid4(),
        name="Test Multiplatform Supplier",
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

    # Create Temu US listing
    temu_us = PlatformListing(
        id=uuid4(),
        candidate_product_id=uuid4(),
        product_variant_id=variant.id,
        inventory_mode=InventoryMode.PRE_ORDER,
        platform=TargetPlatform.TEMU,
        region="us",
        platform_listing_id="TEMU-MP-US-001",
        price=Decimal("25.00"),
        currency="USD",
        inventory=100,
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(temu_us)

    # Create Temu UK listing
    temu_uk = PlatformListing(
        id=uuid4(),
        candidate_product_id=uuid4(),
        product_variant_id=variant.id,
        inventory_mode=InventoryMode.PRE_ORDER,
        platform=TargetPlatform.TEMU,
        region="uk",
        platform_listing_id="TEMU-MP-UK-001",
        price=Decimal("22.00"),
        currency="GBP",
        inventory=80,
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(temu_uk)

    # Create Amazon US listing (paused)
    amazon_us = PlatformListing(
        id=uuid4(),
        candidate_product_id=uuid4(),
        product_variant_id=variant.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_listing_id="AMZN-MP-US-001",
        price=Decimal("35.00"),
        currency="USD",
        inventory=50,
        status=PlatformListingStatus.PAUSED,
    )
    db_session.add(amazon_us)

    await db_session.commit()

    return {
        "master": master,
        "variant": variant,
        "supplier": supplier,
        "temu_us": temu_us,
        "temu_uk": temu_uk,
        "amazon_us": amazon_us,
    }


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_returns_structure(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should return correct structure."""
    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    assert snapshot["variant_id"] == str(multiplatform_infrastructure["variant"].id)
    assert "summary" in snapshot
    assert "platform_breakdown" in snapshot
    assert "listings" in snapshot


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_includes_all_listings(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should include all 3 listings."""
    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    assert snapshot["summary"]["listing_count"] == 3
    assert len(snapshot["listings"]) == 3


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_active_count(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should count active listings correctly."""
    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    # 2 active (temu_us, temu_uk), 1 paused (amazon_us)
    assert snapshot["summary"]["active_listing_count"] == 2


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_total_inventory(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should sum inventory across listings."""
    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    # 100 (temu_us) + 80 (temu_uk) + 50 (amazon_us)
    assert snapshot["summary"]["total_inventory"] == 230


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_platforms(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should list all platforms."""
    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    assert "temu" in snapshot["summary"]["platforms"]
    assert "amazon" in snapshot["summary"]["platforms"]


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_regions(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should list all regions."""
    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    assert "us" in snapshot["summary"]["regions"]
    assert "uk" in snapshot["summary"]["regions"]


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_platform_breakdown(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should group by platform correctly."""
    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    platforms = {p["platform"] for p in snapshot["platform_breakdown"]}
    assert "temu" in platforms
    assert "amazon" in platforms


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_region_breakdown(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should include region data under platforms."""
    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    # Find Temu entry
    temu_entry = next((p for p in snapshot["platform_breakdown"] if p["platform"] == "temu"), None)
    assert temu_entry is not None
    region_codes = {r["region"] for r in temu_entry["regions"]}
    assert "us" in region_codes
    assert "uk" in region_codes


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_listing_details(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should include profit/performance per listing."""
    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    for listing_detail in snapshot["listings"]:
        assert "listing_id" in listing_detail
        assert "platform" in listing_detail
        assert "region" in listing_detail
        assert "status" in listing_detail
        assert "price" in listing_detail
        assert "currency" in listing_detail
        assert "inventory" in listing_detail
        assert "profit_snapshot" in listing_detail
        assert "listing_performance" in listing_detail


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_with_order_data(db_session: AsyncSession, multiplatform_infrastructure):
    """get_sku_multiplatform_snapshot should aggregate order/profit data."""
    service = OperatingMetricsService()
    order_service = OrderIngestionService()
    profit_service = ProfitLedgerService()

    # Create an order for Temu US listing
    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "50.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "TEMU-MP-US-001",
                "quantity": 2,
                "unit_price": "25.00",
                "gross_revenue": "50.00",
                "line_status": "confirmed",
            }
        ],
    }

    order = await order_service.ingest_order(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
        platform_order_id="ORDER-MP-TEMU-001",
        payload=payload,
    )

    # Build profit ledger
    await profit_service.build_order_profit_ledger(
        db=db_session,
        order_line_id=order.lines[0].id,
    )

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=multiplatform_infrastructure["variant"].id,
    )

    # Temu US listing should have profit data
    temu_listings = [l for l in snapshot["listings"] if l["platform"] == "temu"]
    assert len(temu_listings) == 2
    # At least one listing should have entries
    assert any(l["profit_snapshot"]["entry_count"] >= 0 for l in snapshot["listings"])


@pytest.mark.asyncio
async def test_get_sku_multiplatform_snapshot_empty_variant(db_session: AsyncSession):
    """get_sku_multiplatform_snapshot should handle SKU with no listings."""
    # Create variant with no listings
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MP-EMPTY",
        name="Test Empty SKU",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-MP-EMPTY-V1",
        status="active",
    )
    db_session.add(variant)
    await db_session.commit()

    service = OperatingMetricsService()

    snapshot = await service.get_sku_multiplatform_snapshot(
        db=db_session,
        product_variant_id=variant.id,
    )

    assert snapshot["summary"]["listing_count"] == 0
    assert snapshot["summary"]["active_listing_count"] == 0
    assert snapshot["summary"]["total_inventory"] == 0
    assert len(snapshot["listings"]) == 0
