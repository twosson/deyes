"""Tests for operating metrics service."""
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InventoryMode, OrderLineStatus, OrderStatus, TargetPlatform
from app.db.models import (
    PlatformListing,
    ProductMaster,
    ProductVariant,
    Supplier,
    SupplierOffer,
)
from app.services.order_ingestion_service import OrderIngestionService
from app.services.operating_metrics_service import OperatingMetricsService
from app.services.profit_ledger_service import ProfitLedgerService
from app.services.refund_analysis_service import RefundAnalysisService


@pytest_asyncio.fixture
async def sample_infrastructure(db_session: AsyncSession):
    """Create sample infrastructure for operating metrics tests."""
    # Create master and variant
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-OPS-SKU-001",
        name="Test Operating Metrics Product",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-OPS-SKU-001-V1",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status="active",
    )
    db_session.add(variant)
    await db_session.flush()

    # Create supplier and offer
    supplier = Supplier(
        id=uuid4(),
        name="Test Operating Supplier",
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

    # Create listing
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=uuid4(),
        product_variant_id=variant.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_listing_id="AMZN-OPS-001",
        price=Decimal("30.00"),
        currency="USD",
        inventory=100,
        status="active",
    )
    db_session.add(listing)
    await db_session.commit()

    return {
        "master": master,
        "variant": variant,
        "supplier": supplier,
        "listing": listing,
    }


@pytest.mark.asyncio
async def test_get_sku_operating_snapshot(db_session: AsyncSession, sample_infrastructure):
    """Test SKU-level operating snapshot."""
    # Create orders and profit ledgers
    order_service = OrderIngestionService()
    profit_service = ProfitLedgerService()
    refund_service = RefundAnalysisService()
    metrics_service = OperatingMetricsService()

    # Create order
    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "30.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "AMZN-OPS-001",
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
        platform_order_id="ORDER-OPS-SKU-001",
        payload=payload,
    )

    # Build profit ledger
    await profit_service.build_order_profit_ledger(
        db=db_session,
        order_line_id=order.lines[0].id,
    )

    # Create refund
    await refund_service.create_refund_case(
        db=db_session,
        platform_order_id=order.id,
        refund_amount=Decimal("10.00"),
        currency="USD",
        refund_reason=RefundReason.QUALITY_ISSUE,
        platform_order_line_id=order.lines[0].id,
        product_variant_id=sample_infrastructure["variant"].id,
    )

    # Get SKU snapshot
    snapshot = await metrics_service.get_sku_operating_snapshot(
        db=db_session,
        product_variant_id=sample_infrastructure["variant"].id,
    )

    assert snapshot["variant_id"] == str(sample_infrastructure["variant"].id)
    assert "profit_snapshot" in snapshot
    assert "refund_rate" in snapshot
    assert "refund_reasons" in snapshot
    assert snapshot["profit_snapshot"]["entry_count"] == 1
    assert snapshot["profit_snapshot"]["total_gross_revenue"] == 30.0


@pytest.mark.asyncio
async def test_get_listing_operating_snapshot(db_session: AsyncSession, sample_infrastructure):
    """Test listing-level operating snapshot."""
    # Create orders and profit ledgers
    order_service = OrderIngestionService()
    profit_service = ProfitLedgerService()
    metrics_service = OperatingMetricsService()

    # Create order
    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "30.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "AMZN-OPS-001",
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
        platform_order_id="ORDER-OPS-LISTING-001",
        payload=payload,
    )

    # Build profit ledger
    await profit_service.build_order_profit_ledger(
        db=db_session,
        order_line_id=order.lines[0].id,
    )

    # Get listing snapshot
    snapshot = await metrics_service.get_listing_operating_snapshot(
        db=db_session,
        platform_listing_id=sample_infrastructure["listing"].id,
    )

    assert snapshot["listing_id"] == str(sample_infrastructure["listing"].id)
    assert "profit_snapshot" in snapshot
    assert "refund_rate" in snapshot
    assert "refund_reasons" in snapshot
    assert "listing_performance" in snapshot
    assert snapshot["profit_snapshot"]["entry_count"] == 1
    assert snapshot["profit_snapshot"]["total_gross_revenue"] == 30.0


@pytest.mark.asyncio
async def test_get_supplier_operating_snapshot(db_session: AsyncSession, sample_infrastructure):
    """Test supplier-level operating snapshot."""
    # Create orders and profit ledgers
    order_service = OrderIngestionService()
    profit_service = ProfitLedgerService()
    metrics_service = OperatingMetricsService()

    # Create order
    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "30.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "AMZN-OPS-001",
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
        platform_order_id="ORDER-OPS-SUPPLIER-001",
        payload=payload,
    )

    # Build profit ledger
    await profit_service.build_order_profit_ledger(
        db=db_session,
        order_line_id=order.lines[0].id,
    )

    # Get supplier snapshot
    snapshot = await metrics_service.get_supplier_operating_snapshot(
        db=db_session,
        supplier_id=sample_infrastructure["supplier"].id,
    )

    assert snapshot["supplier_id"] == str(sample_infrastructure["supplier"].id)
    assert "profit_snapshot" in snapshot
    assert snapshot["profit_snapshot"]["entry_count"] == 1
    assert snapshot["profit_snapshot"]["total_gross_revenue"] == 30.0


from app.core.enums import RefundReason
