"""Phase 4 order/fulfillment/inventory integration tests."""
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    InventoryMode,
    OrderLineStatus,
    OrderStatus,
    RefundReason,
    RefundStatus,
    TargetPlatform,
)
from app.db.models import (
    InventoryLevel,
    InventoryReservation,
    PlatformListing,
    ProductMaster,
    ProductVariant,
    Supplier,
    SupplierOffer,
)
from app.services.inventory_allocator import InventoryAllocator
from app.services.order_ingestion_service import OrderIngestionService
from app.services.profit_ledger_service import ProfitLedgerService
from app.services.refund_analysis_service import RefundAnalysisService


@pytest_asyncio.fixture
async def sample_variant_with_supplier(db_session: AsyncSession):
    """Create a sample variant with supplier offer."""
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-SKU-001",
        name="Test Product",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-001-V1",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status="active",
    )
    db_session.add(variant)
    await db_session.flush()

    supplier = Supplier(
        id=uuid4(),
        name="Test Supplier",
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
    await db_session.commit()

    return variant


@pytest_asyncio.fixture
async def sample_listing(db_session: AsyncSession, sample_variant_with_supplier):
    """Create a sample platform listing."""
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=uuid4(),
        product_variant_id=sample_variant_with_supplier.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_listing_id="AMZN-TEST-001",
        price=Decimal("25.00"),
        currency="USD",
        inventory=100,
        status="active",
    )
    db_session.add(listing)
    await db_session.commit()

    return listing


@pytest.mark.asyncio
async def test_order_ingestion_idempotency(db_session: AsyncSession, sample_listing):
    """Test order ingestion with idempotency check."""
    service = OrderIngestionService()

    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "25.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "AMZN-TEST-001",
                "quantity": 1,
                "unit_price": "25.00",
                "gross_revenue": "25.00",
                "discount_amount": "0.00",
                "line_status": "confirmed",
            }
        ],
    }

    # First ingestion
    order1 = await service.ingest_order(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_order_id="ORDER-001",
        payload=payload,
    )

    assert order1 is not None
    assert order1.platform_order_id == "ORDER-001"
    assert order1.order_status == OrderStatus.CONFIRMED
    assert len(order1.lines) == 1

    # Second ingestion (should return existing order)
    order2 = await service.ingest_order(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_order_id="ORDER-001",
        payload=payload,
    )

    assert order2.id == order1.id  # Same order


@pytest.mark.asyncio
async def test_order_line_sku_mapping(db_session: AsyncSession, sample_listing):
    """Test order line SKU/listing mapping."""
    service = OrderIngestionService()

    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "25.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "AMZN-TEST-001",
                "quantity": 1,
                "unit_price": "25.00",
                "gross_revenue": "25.00",
                "discount_amount": "0.00",
                "line_status": "confirmed",
            }
        ],
    }

    order = await service.ingest_order(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_order_id="ORDER-002",
        payload=payload,
    )

    line = order.lines[0]
    assert line.platform_sku == "AMZN-TEST-001"
    assert line.platform_listing_id == sample_listing.id
    assert line.product_variant_id == sample_listing.product_variant_id


@pytest.mark.asyncio
async def test_pre_order_creates_reservation(db_session: AsyncSession, sample_variant_with_supplier):
    """Test pre_order order creates inventory reservation."""
    # Create pre_order listing
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=uuid4(),
        product_variant_id=sample_variant_with_supplier.id,
        inventory_mode=InventoryMode.PRE_ORDER,
        platform=TargetPlatform.TEMU,
        region="us",
        platform_listing_id="TEMU-TEST-001",
        price=Decimal("20.00"),
        currency="USD",
        inventory=0,
        status="active",
    )
    db_session.add(listing)
    await db_session.commit()

    service = OrderIngestionService()

    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "20.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "TEMU-TEST-001",
                "quantity": 5,
                "unit_price": "20.00",
                "gross_revenue": "100.00",
                "discount_amount": "0.00",
                "line_status": "confirmed",
            }
        ],
    }

    order, inventory_actions = await service.ingest_order_with_inventory(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
        platform_order_id="ORDER-PRE-001",
        payload=payload,
    )

    assert len(inventory_actions["reservations_created"]) == 1
    assert len(inventory_actions["outbound_movements"]) == 0
    assert inventory_actions["reservations_created"][0]["quantity"] == 5

    # Verify reservation created
    from sqlalchemy import select

    stmt = select(InventoryReservation).where(
        InventoryReservation.variant_id == sample_variant_with_supplier.id
    )
    result = await db_session.execute(stmt)
    reservation = result.scalar_one_or_none()

    assert reservation is not None
    assert reservation.quantity == 5
    assert reservation.reference_type == "platform_order"


@pytest.mark.asyncio
async def test_stock_first_records_outbound(db_session: AsyncSession, sample_listing, sample_variant_with_supplier):
    """Test stock_first order records outbound movement."""
    # Add inventory
    allocator = InventoryAllocator()
    await allocator.record_inbound(db_session, sample_variant_with_supplier.id, quantity=100)

    service = OrderIngestionService()

    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "25.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "AMZN-TEST-001",
                "quantity": 2,
                "unit_price": "25.00",
                "gross_revenue": "50.00",
                "discount_amount": "0.00",
                "line_status": "confirmed",
            }
        ],
    }

    order, inventory_actions = await service.ingest_order_with_inventory(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_order_id="ORDER-STOCK-001",
        payload=payload,
    )

    assert len(inventory_actions["reservations_created"]) == 0
    assert len(inventory_actions["outbound_movements"]) == 1
    assert inventory_actions["outbound_movements"][0]["quantity"] == 2

    # Verify inventory reduced
    from sqlalchemy import select

    stmt = select(InventoryLevel).where(InventoryLevel.variant_id == sample_variant_with_supplier.id)
    result = await db_session.execute(stmt)
    level = result.scalar_one_or_none()

    assert level is not None
    assert level.available_quantity == 98  # 100 - 2


@pytest.mark.asyncio
async def test_profit_ledger_creation(db_session: AsyncSession, sample_listing, sample_variant_with_supplier):
    """Test profit ledger creation from order line."""
    # Create order
    order_service = OrderIngestionService()

    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "25.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "AMZN-TEST-001",
                "quantity": 1,
                "unit_price": "25.00",
                "gross_revenue": "25.00",
                "discount_amount": "0.00",
                "line_status": "confirmed",
            }
        ],
    }

    order = await order_service.ingest_order(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_order_id="ORDER-PROFIT-001",
        payload=payload,
    )

    # Build profit ledger
    profit_service = ProfitLedgerService()
    ledger = await profit_service.build_order_profit_ledger(
        db=db_session,
        order_line_id=order.lines[0].id,
    )

    assert ledger is not None
    assert ledger.gross_revenue == Decimal("25.00")
    assert ledger.platform_fee == Decimal("2.50")  # 10% of 25.00
    assert ledger.net_profit == Decimal("12.50")  # 25.00 - 10.00 (supplier) - 2.50 (fee)
    assert ledger.profit_margin == Decimal("50.00")  # 12.50 / 25.00 * 100


@pytest.mark.asyncio
async def test_refund_adjustment(db_session: AsyncSession, sample_listing, sample_variant_with_supplier):
    """Test refund adjustment to profit ledger."""
    # Create order and profit ledger
    order_service = OrderIngestionService()

    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "25.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "AMZN-TEST-001",
                "quantity": 1,
                "unit_price": "25.00",
                "gross_revenue": "25.00",
                "discount_amount": "0.00",
                "line_status": "confirmed",
            }
        ],
    }

    order = await order_service.ingest_order(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_order_id="ORDER-REFUND-001",
        payload=payload,
    )

    profit_service = ProfitLedgerService()
    ledger = await profit_service.build_order_profit_ledger(
        db=db_session,
        order_line_id=order.lines[0].id,
    )

    original_net_profit = ledger.net_profit

    # Apply refund
    updated_ledger = await profit_service.apply_refund_adjustment(
        db=db_session,
        ledger_id=ledger.id,
        refund_amount=Decimal("10.00"),
    )

    assert updated_ledger.refund_loss == Decimal("10.00")
    assert updated_ledger.net_profit == original_net_profit - Decimal("10.00")


@pytest.mark.asyncio
async def test_refund_case_creation(db_session: AsyncSession, sample_listing, sample_variant_with_supplier):
    """Test refund case creation."""
    # Create order
    order_service = OrderIngestionService()

    payload = {
        "order_status": "confirmed",
        "currency": "USD",
        "total_amount": "25.00",
        "ordered_at": "2026-03-29T12:00:00Z",
        "lines": [
            {
                "platform_sku": "AMZN-TEST-001",
                "quantity": 1,
                "unit_price": "25.00",
                "gross_revenue": "25.00",
                "discount_amount": "0.00",
                "line_status": "confirmed",
            }
        ],
    }

    order = await order_service.ingest_order(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_order_id="ORDER-REFUND-CASE-001",
        payload=payload,
    )

    # Create refund case
    refund_service = RefundAnalysisService()
    refund_case = await refund_service.create_refund_case(
        db=db_session,
        platform_order_id=order.id,
        refund_amount=Decimal("25.00"),
        currency="USD",
        refund_reason=RefundReason.QUALITY_ISSUE,
        platform_order_line_id=order.lines[0].id,
        product_variant_id=sample_variant_with_supplier.id,
        issue_type="quality_issue",
        attributed_to="supplier",
    )

    assert refund_case is not None
    assert refund_case.refund_amount == Decimal("25.00")
    assert refund_case.refund_reason == RefundReason.QUALITY_ISSUE
    assert refund_case.refund_status == RefundStatus.PENDING
    assert refund_case.attributed_to == "supplier"


@pytest.mark.asyncio
async def test_profit_snapshot(db_session: AsyncSession, sample_listing, sample_variant_with_supplier):
    """Test profit snapshot aggregation."""
    # Create multiple orders
    order_service = OrderIngestionService()
    profit_service = ProfitLedgerService()

    for i in range(3):
        payload = {
            "order_status": "confirmed",
            "currency": "USD",
            "total_amount": "25.00",
            "ordered_at": "2026-03-29T12:00:00Z",
            "lines": [
                {
                    "platform_sku": "AMZN-TEST-001",
                    "quantity": 1,
                    "unit_price": "25.00",
                    "gross_revenue": "25.00",
                    "discount_amount": "0.00",
                    "line_status": "confirmed",
                }
            ],
        }

        order = await order_service.ingest_order(
            db=db_session,
            platform=TargetPlatform.AMAZON,
            region="us",
            platform_order_id=f"ORDER-SNAPSHOT-{i:03d}",
            payload=payload,
        )

        await profit_service.build_order_profit_ledger(
            db=db_session,
            order_line_id=order.lines[0].id,
        )

    # Get profit snapshot
    snapshot = await profit_service.get_profit_snapshot(
        db=db_session,
        product_variant_id=sample_variant_with_supplier.id,
    )

    assert snapshot["entry_count"] == 3
    assert snapshot["total_gross_revenue"] == 75.00  # 25.00 * 3
    assert snapshot["total_net_profit"] == 37.50  # 12.50 * 3
    assert snapshot["overall_margin"] == 50.00
