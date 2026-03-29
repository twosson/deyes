"""Tests for refund analysis service."""
from datetime import date, datetime, timezone
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
    PlatformListing,
    PlatformOrder,
    PlatformOrderLine,
    ProductMaster,
    ProductVariant,
    RefundCase,
    Supplier,
    SupplierOffer,
)
from app.services.profit_ledger_service import ProfitLedgerService
from app.services.refund_analysis_service import RefundAnalysisService


@pytest_asyncio.fixture
async def sample_order_with_lines(db_session: AsyncSession):
    """Create a sample order with lines."""
    # Create master and variant
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-SKU-REFUND-001",
        name="Test Refund Product",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-REFUND-001-V1",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status="active",
    )
    db_session.add(variant)
    await db_session.flush()

    # Create supplier and offer
    supplier = Supplier(
        id=uuid4(),
        name="Test Refund Supplier",
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
        platform_listing_id="AMZN-REFUND-001",
        price=Decimal("30.00"),
        currency="USD",
        inventory=100,
        status="active",
    )
    db_session.add(listing)

    # Create order
    order = PlatformOrder(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="us",
        platform_order_id="ORDER-REFUND-001",
        idempotency_key="order:amazon:ORDER-REFUND-001",
        order_status=OrderStatus.CONFIRMED,
        currency="USD",
        total_amount=Decimal("60.00"),
        ordered_at=datetime.now(timezone.utc),
    )
    db_session.add(order)
    await db_session.flush()

    # Create order lines
    line1 = PlatformOrderLine(
        id=uuid4(),
        order_id=order.id,
        platform_listing_id=listing.id,
        product_variant_id=variant.id,
        platform_sku="AMZN-REFUND-001",
        quantity=2,
        unit_price=Decimal("30.00"),
        gross_revenue=Decimal("60.00"),
        line_status=OrderLineStatus.CONFIRMED,
    )
    db_session.add(line1)

    await db_session.commit()

    return {
        "order": order,
        "line1": line1,
        "variant": variant,
        "listing": listing,
    }


@pytest.mark.asyncio
async def test_get_refund_rate(db_session: AsyncSession, sample_order_with_lines):
    """Test refund rate calculation."""
    refund_service = RefundAnalysisService()

    # Create refund case
    refund_case = await refund_service.create_refund_case(
        db=db_session,
        platform_order_id=sample_order_with_lines["order"].id,
        refund_amount=Decimal("30.00"),
        currency="USD",
        refund_reason=RefundReason.QUALITY_ISSUE,
        platform_order_line_id=sample_order_with_lines["line1"].id,
        product_variant_id=sample_order_with_lines["variant"].id,
    )

    # Get refund rate
    refund_rate = await refund_service.get_refund_rate(
        db=db_session,
        product_variant_id=sample_order_with_lines["variant"].id,
    )

    assert refund_rate["total_orders"] == 1
    assert refund_rate["refunded_orders"] == 1
    assert refund_rate["refund_rate"] == 100.0
    assert refund_rate["total_refund_amount"] == 30.0


@pytest.mark.asyncio
async def test_summarize_refund_reasons(db_session: AsyncSession, sample_order_with_lines):
    """Test refund reasons summarization."""
    refund_service = RefundAnalysisService()

    # Create multiple refund cases
    await refund_service.create_refund_case(
        db=db_session,
        platform_order_id=sample_order_with_lines["order"].id,
        refund_amount=Decimal("30.00"),
        currency="USD",
        refund_reason=RefundReason.QUALITY_ISSUE,
        platform_order_line_id=sample_order_with_lines["line1"].id,
        product_variant_id=sample_order_with_lines["variant"].id,
        attributed_to="supplier",
    )

    # Get refund reasons summary
    summary = await refund_service.summarize_refund_reasons(
        db=db_session,
        product_variant_id=sample_order_with_lines["variant"].id,
    )

    assert len(summary) == 1
    assert summary[0]["refund_reason"] == "quality_issue"
    assert summary[0]["count"] == 1
    assert summary[0]["total_amount"] == 30.0
    assert summary[0]["attributed_to"] == "supplier"


@pytest.mark.asyncio
async def test_link_refund_to_profit_ledger(db_session: AsyncSession, sample_order_with_lines):
    """Test linking refund case to profit ledger."""
    refund_service = RefundAnalysisService()
    profit_service = ProfitLedgerService()

    # Create profit ledger
    ledger = await profit_service.build_order_profit_ledger(
        db=db_session,
        order_line_id=sample_order_with_lines["line1"].id,
    )

    original_net_profit = ledger.net_profit

    # Create refund case
    refund_case = await refund_service.create_refund_case(
        db=db_session,
        platform_order_id=sample_order_with_lines["order"].id,
        refund_amount=Decimal("30.00"),
        currency="USD",
        refund_reason=RefundReason.QUALITY_ISSUE,
        platform_order_line_id=sample_order_with_lines["line1"].id,
        product_variant_id=sample_order_with_lines["variant"].id,
    )

    # Link refund to profit ledger
    updated_ledger = await refund_service.link_refund_to_profit_ledger(
        db=db_session,
        refund_case_id=refund_case.id,
    )

    assert updated_ledger.refund_loss == Decimal("30.00")
    assert updated_ledger.net_profit == original_net_profit - Decimal("30.00")


@pytest.mark.asyncio
async def test_get_refund_rate_by_listing(db_session: AsyncSession, sample_order_with_lines):
    """Test refund rate calculation by listing."""
    refund_service = RefundAnalysisService()

    # Create refund case
    await refund_service.create_refund_case(
        db=db_session,
        platform_order_id=sample_order_with_lines["order"].id,
        refund_amount=Decimal("30.00"),
        currency="USD",
        refund_reason=RefundReason.QUALITY_ISSUE,
        platform_order_line_id=sample_order_with_lines["line1"].id,
        product_variant_id=sample_order_with_lines["variant"].id,
    )

    # Get refund rate by listing
    refund_rate = await refund_service.get_refund_rate(
        db=db_session,
        platform_listing_id=sample_order_with_lines["listing"].id,
    )

    assert refund_rate["total_orders"] == 1
    assert refund_rate["refunded_orders"] == 1
    assert refund_rate["refund_rate"] == 100.0
