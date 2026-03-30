"""Tests for AnomalyDetectionService.

Tests cover:
- detect_sku_anomalies: sales_drop, refund_spike, margin_collapse, stockout_risk
- detect_listing_anomalies: ctr_drop, cvr_drop
- detect_supplier_anomalies: supplier_delay, supplier_fulfillment_issues
- detect_global_anomalies: aggregation across all SKUs
- save_anomaly_signal: persisting anomaly signals
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    ActionType,
    ActionExecutionStatus,
    OrderStatus,
    PlatformListingStatus,
    ProductVariantStatus,
    PurchaseOrderStatus,
    RefundReason,
    RefundStatus,
    SkuLifecycleState,
    SupplierStatus,
    TargetPlatform,
)
from app.db.models import (
    ActionExecutionLog,
    AnomalyDetectionSignal,
    InventoryLevel,
    ListingPerformanceDaily,
    PlatformListing,
    PlatformOrder,
    PlatformOrderLine,
    ProductMaster,
    ProductVariant,
    ProfitLedger,
    PurchaseOrder,
    RefundCase,
    Supplier,
    SupplierOffer,
)
from app.services.anomaly_detection_service import AnomalyDetectionService


@pytest_asyncio.fixture
async def sample_product_variant(db_session: AsyncSession):
    """Create a sample product variant with master."""
    master = ProductMaster(
        id=uuid4(),
        internal_sku=f"TEST-ANOMALY-SKU-{uuid4().hex[:8]}",
        name="Test Anomaly Product",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku=f"TEST-ANOMALY-SKU-{uuid4().hex[:8]}-V1",
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.commit()

    return variant


@pytest_asyncio.fixture
async def sample_platform_listing(db_session: AsyncSession, sample_product_variant, sample_candidate):
    """Create a sample platform listing."""
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        product_variant_id=sample_product_variant.id,
        platform=TargetPlatform.TEMU,
        region="US",
        status=PlatformListingStatus.ACTIVE,
        price=Decimal("50.00"),
        currency="USD",
    )
    db_session.add(listing)
    await db_session.commit()

    return listing


@pytest_asyncio.fixture
async def sample_supplier(db_session: AsyncSession):
    """Create a sample supplier."""
    supplier = Supplier(
        id=uuid4(),
        name="Test Anomaly Supplier",
        status=SupplierStatus.ACTIVE,
    )
    db_session.add(supplier)
    await db_session.commit()

    return supplier


@pytest_asyncio.fixture
async def profit_ledger_data(db_session: AsyncSession, sample_product_variant):
    """Create profit ledger entries for testing."""
    today = date.today()

    # Create entries for the past 16 days
    # Recent window in service is inclusive: today-7 through today (8 days)
    for i in range(8):
        ledger = ProfitLedger(
            id=uuid4(),
            product_variant_id=sample_product_variant.id,
            snapshot_date=today - timedelta(days=i),
            gross_revenue=Decimal("50.00"),  # Lower recent revenue
            net_profit=Decimal("10.00"),
            profit_margin=Decimal("20.00"),
        )
        db_session.add(ledger)

    # Prior window in service is inclusive: today-15 through today-8 (8 days)
    for i in range(8, 16):
        ledger = ProfitLedger(
            id=uuid4(),
            product_variant_id=sample_product_variant.id,
            snapshot_date=today - timedelta(days=i),
            gross_revenue=Decimal("100.00"),  # Higher prior revenue
            net_profit=Decimal("30.00"),
            profit_margin=Decimal("30.00"),
        )
        db_session.add(ledger)

    await db_session.commit()

    return {"variant_id": sample_product_variant.id}


@pytest_asyncio.fixture
async def refund_cases_data(db_session: AsyncSession, sample_product_variant):
    """Create refund cases for testing refund spike."""
    today = date.today()

    # Recent refunds (high count)
    for i in range(5):
        order = PlatformOrder(
            id=uuid4(),
            platform=TargetPlatform.TEMU,
            region="US",
            platform_order_id=f"ORDER-REFUND-{i}",
            idempotency_key=f"IDEMPOTENCY-REFUND-{i}",
            order_status=OrderStatus.REFUNDED,
            currency="USD",
            total_amount=Decimal("50.00"),
            ordered_at=datetime.utcnow() - timedelta(days=i),
        )
        db_session.add(order)
        await db_session.flush()

        refund = RefundCase(
            id=uuid4(),
            platform_order_id=order.id,
            product_variant_id=sample_product_variant.id,
            refund_amount=Decimal("20.00"),
            currency="USD",
            refund_reason=RefundReason.QUALITY_ISSUE,
            refund_status=RefundStatus.APPROVED,
            requested_at=datetime.utcnow() - timedelta(days=i),
        )
        db_session.add(refund)

    # Prior refunds (low count) - 17-20 days ago (outside recent window)
    for i in range(17, 19):
        order = PlatformOrder(
            id=uuid4(),
            platform=TargetPlatform.TEMU,
            region="US",
            platform_order_id=f"ORDER-REFUND-PRIOR-{i}",
            idempotency_key=f"IDEMPOTENCY-REFUND-PRIOR-{i}",
            order_status=OrderStatus.REFUNDED,
            currency="USD",
            total_amount=Decimal("50.00"),
            ordered_at=datetime.utcnow() - timedelta(days=i),
        )
        db_session.add(order)
        await db_session.flush()

        refund = RefundCase(
            id=uuid4(),
            platform_order_id=order.id,
            product_variant_id=sample_product_variant.id,
            refund_amount=Decimal("15.00"),
            currency="USD",
            refund_reason=RefundReason.CHANGED_MIND,
            refund_status=RefundStatus.COMPLETED,
            requested_at=datetime.utcnow() - timedelta(days=i),
        )
        db_session.add(refund)

    await db_session.commit()

    return {"variant_id": sample_product_variant.id}


@pytest_asyncio.fixture
async def listing_performance_data(db_session: AsyncSession, sample_platform_listing):
    """Create listing performance data for CTR/CVR testing."""
    today = date.today()

    # Recent 7 days: lower CTR/CVR (drop scenario)
    for i in range(7):
        perf = ListingPerformanceDaily(
            id=uuid4(),
            listing_id=sample_platform_listing.id,
            metric_date=today - timedelta(days=i),
            impressions=1000,
            clicks=20,  # 2% CTR (drop from 5%)
            orders=1,   # 5% CVR (drop from 10%)
        )
        db_session.add(perf)

    # Prior 7 days: higher CTR/CVR
    for i in range(7, 14):
        perf = ListingPerformanceDaily(
            id=uuid4(),
            listing_id=sample_platform_listing.id,
            metric_date=today - timedelta(days=i),
            impressions=1000,
            clicks=50,  # 5% CTR
            orders=5,   # 10% CVR
        )
        db_session.add(perf)

    await db_session.commit()

    return {"listing_id": sample_platform_listing.id}


@pytest_asyncio.fixture
async def inventory_data(db_session: AsyncSession, sample_product_variant):
    """Create inventory data for stockout risk testing."""
    inventory = InventoryLevel(
        id=uuid4(),
        variant_id=sample_product_variant.id,
        available_quantity=5,  # Low inventory
        reserved_quantity=0,
        damaged_quantity=0,
    )
    db_session.add(inventory)
    await db_session.commit()

    return inventory


@pytest_asyncio.fixture
async def supplier_with_offers(db_session: AsyncSession, sample_product_variant, sample_supplier):
    """Create supplier with offers linked to variant."""
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

    return offer


class TestAnomalyDetectionServiceInit:
    """Test AnomalyDetectionService initialization."""

    def test_init(self):
        """Test service initializes correctly."""
        service = AnomalyDetectionService()
        assert service is not None
        assert service.SALES_DROP_THRESHOLD == Decimal("0.30")
        assert service.REFUND_SPIKE_THRESHOLD == Decimal("0.50")
        assert service.MARGIN_COLLAPSE_THRESHOLD == Decimal("0.15")
        assert service.STOCKOUT_RISK_DAYS == 7


class TestDetectSkuAnomalies:
    """Tests for detect_sku_anomalies method."""

    @pytest.mark.asyncio
    async def test_detect_sku_anomalies_no_data(self, db_session: AsyncSession):
        """Test with no data returns empty anomalies."""
        service = AnomalyDetectionService()
        variant_id = uuid4()

        anomalies = await service.detect_sku_anomalies(
            db=db_session,
            product_variant_id=variant_id,
            lookback_days=30,
        )

        assert isinstance(anomalies, list)
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_detect_sales_drop_anomaly(
        self, db_session: AsyncSession, profit_ledger_data
    ):
        """Test sales drop detection when revenue declines significantly."""
        service = AnomalyDetectionService()
        variant_id = profit_ledger_data["variant_id"]

        anomalies = await service.detect_sku_anomalies(
            db=db_session,
            product_variant_id=variant_id,
            lookback_days=30,
        )

        # Should detect sales drop (50% decline > 30% threshold)
        sales_drop_anomalies = [a for a in anomalies if a["type"] == "sales_drop"]
        assert len(sales_drop_anomalies) >= 1

        anomaly = sales_drop_anomalies[0]
        assert "severity" in anomaly
        assert anomaly["severity"] in ["critical", "high", "medium", "low"]
        assert "details" in anomaly
        assert "decline_percentage" in anomaly["details"]
        assert anomaly["details"]["decline_percentage"] >= 30.0

    @pytest.mark.asyncio
    async def test_detect_no_sales_drop_when_stable(self, db_session: AsyncSession, sample_product_variant):
        """Test no sales drop anomaly when revenue is stable."""
        today = date.today()

        # Create stable revenue data
        for i in range(14):
            ledger = ProfitLedger(
                id=uuid4(),
                product_variant_id=sample_product_variant.id,
                snapshot_date=today - timedelta(days=i),
                gross_revenue=Decimal("100.00"),  # Stable revenue
                net_profit=Decimal("30.00"),
                profit_margin=Decimal("30.00"),
            )
            db_session.add(ledger)

        await db_session.commit()

        service = AnomalyDetectionService()
        anomalies = await service.detect_sku_anomalies(
            db=db_session,
            product_variant_id=sample_product_variant.id,
            lookback_days=30,
        )

        sales_drop_anomalies = [a for a in anomalies if a["type"] == "sales_drop"]
        assert len(sales_drop_anomalies) == 0

    @pytest.mark.asyncio
    async def test_detect_margin_collapse_anomaly(
        self, db_session: AsyncSession, sample_product_variant
    ):
        """Test margin collapse detection when margin falls below threshold."""
        today = date.today()

        # Create entries with low margin (< 15%)
        for i in range(14):
            ledger = ProfitLedger(
                id=uuid4(),
                product_variant_id=sample_product_variant.id,
                snapshot_date=today - timedelta(days=i),
                gross_revenue=Decimal("100.00"),
                net_profit=Decimal("10.00"),  # 10% margin (< 15% threshold)
                profit_margin=Decimal("10.00"),
            )
            db_session.add(ledger)

        await db_session.commit()

        service = AnomalyDetectionService()
        anomalies = await service.detect_sku_anomalies(
            db=db_session,
            product_variant_id=sample_product_variant.id,
            lookback_days=30,
        )

        margin_anomalies = [a for a in anomalies if a["type"] == "margin_collapse"]
        assert len(margin_anomalies) >= 1

        anomaly = margin_anomalies[0]
        assert anomaly["severity"] == "critical"
        assert "average_margin" in anomaly["details"]

    @pytest.mark.asyncio
    async def test_detect_stockout_risk_critical(
        self, db_session: AsyncSession, sample_product_variant
    ):
        """Test stockout risk detection with zero inventory."""
        # Create revenue history (required by service)
        today = date.today()
        for i in range(14):
            ledger = ProfitLedger(
                id=uuid4(),
                product_variant_id=sample_product_variant.id,
                snapshot_date=today - timedelta(days=i),
                gross_revenue=Decimal("100.00"),
                net_profit=Decimal("30.00"),
                profit_margin=Decimal("30.00"),
            )
            db_session.add(ledger)

        inventory = InventoryLevel(
            id=uuid4(),
            variant_id=sample_product_variant.id,
            available_quantity=0,  # Out of stock
            reserved_quantity=0,
            damaged_quantity=0,
        )
        db_session.add(inventory)
        await db_session.commit()

        service = AnomalyDetectionService()
        anomalies = await service.detect_sku_anomalies(
            db=db_session,
            product_variant_id=sample_product_variant.id,
            lookback_days=30,
        )

        stockout_anomalies = [a for a in anomalies if a["type"] == "stockout_risk"]
        assert len(stockout_anomalies) >= 1

        anomaly = stockout_anomalies[0]
        assert anomaly["severity"] == "critical"
        assert anomaly["details"]["status"] == "out_of_stock"

    @pytest.mark.asyncio
    async def test_detect_stockout_risk_low_inventory(
        self, db_session: AsyncSession, sample_product_variant
    ):
        """Test stockout risk detection with low inventory."""
        # Create revenue history (required by service)
        today = date.today()
        for i in range(14):
            ledger = ProfitLedger(
                id=uuid4(),
                product_variant_id=sample_product_variant.id,
                snapshot_date=today - timedelta(days=i),
                gross_revenue=Decimal("100.00"),
                net_profit=Decimal("30.00"),
                profit_margin=Decimal("30.00"),
            )
            db_session.add(ledger)

        inventory = InventoryLevel(
            id=uuid4(),
            variant_id=sample_product_variant.id,
            available_quantity=3,  # Low inventory
            reserved_quantity=0,
            damaged_quantity=0,
        )
        db_session.add(inventory)
        await db_session.commit()

        service = AnomalyDetectionService()
        anomalies = await service.detect_sku_anomalies(
            db=db_session,
            product_variant_id=sample_product_variant.id,
            lookback_days=30,
        )

        stockout_anomalies = [a for a in anomalies if a["type"] == "stockout_risk"]
        assert len(stockout_anomalies) >= 1

        anomaly = stockout_anomalies[0]
        assert anomaly["severity"] == "high"
        assert anomaly["details"]["status"] == "low_inventory"


class TestDetectRefundSpike:
    """Tests for refund spike detection."""

    @pytest.mark.asyncio
    async def test_detect_refund_spike_anomaly(
        self, db_session: AsyncSession, refund_cases_data
    ):
        """Test refund spike detection when refunds increase significantly."""
        service = AnomalyDetectionService()
        variant_id = refund_cases_data["variant_id"]

        anomalies = await service.detect_sku_anomalies(
            db=db_session,
            product_variant_id=variant_id,
            lookback_days=30,
        )

        refund_anomalies = [a for a in anomalies if a["type"] == "refund_spike"]
        assert len(refund_anomalies) >= 1

        anomaly = refund_anomalies[0]
        assert anomaly["severity"] in ["critical", "high", "medium", "low"]
        assert "recent_refunds" in anomaly["details"]
        assert anomaly["details"]["recent_refunds"] == 5

    @pytest.mark.asyncio
    async def test_detect_refund_spike_new_cases(
        self, db_session: AsyncSession, sample_product_variant
    ):
        """Test refund spike detection for new refund cases (no prior refunds)."""
        today = date.today()

        # Create recent refunds without prior refunds
        for i in range(5):
            order = PlatformOrder(
                id=uuid4(),
                platform=TargetPlatform.TEMU,
                region="US",
                platform_order_id=f"ORDER-NEW-REFUND-{i}",
                idempotency_key=f"IDEMPOTENCY-NEW-REFUND-{i}",
                order_status=OrderStatus.REFUNDED,
                currency="USD",
                total_amount=Decimal("50.00"),
                ordered_at=datetime.utcnow() - timedelta(days=i),
            )
            db_session.add(order)
            await db_session.flush()

            refund = RefundCase(
                id=uuid4(),
                platform_order_id=order.id,
                product_variant_id=sample_product_variant.id,
                refund_amount=Decimal("20.00"),
                currency="USD",
                refund_reason=RefundReason.QUALITY_ISSUE,
                refund_status=RefundStatus.APPROVED,
                requested_at=datetime.utcnow() - timedelta(days=i),
            )
            db_session.add(refund)

        await db_session.commit()

        service = AnomalyDetectionService()
        anomalies = await service.detect_sku_anomalies(
            db=db_session,
            product_variant_id=sample_product_variant.id,
            lookback_days=30,
        )

        refund_anomalies = [a for a in anomalies if a["type"] == "refund_spike"]
        assert len(refund_anomalies) >= 1
        assert refund_anomalies[0]["details"]["increase_type"] == "new_refund_cases"


class TestDetectListingAnomalies:
    """Tests for listing-specific anomaly detection."""

    @pytest.mark.asyncio
    async def test_detect_listing_anomalies_no_data(self, db_session: AsyncSession):
        """Test with no listing data returns empty anomalies."""
        service = AnomalyDetectionService()
        listing_id = uuid4()

        anomalies = await service.detect_listing_anomalies(
            db=db_session,
            listing_id=listing_id,
            lookback_days=30,
        )

        assert isinstance(anomalies, list)
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_detect_ctr_drop_anomaly(
        self, db_session: AsyncSession, listing_performance_data
    ):
        """Test CTR drop detection when CTR declines significantly."""
        from sqlalchemy import select

        service = AnomalyDetectionService()
        listing_id = listing_performance_data["listing_id"]

        # Get the listing
        stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
        result = await db_session.execute(stmt)
        listing = result.scalar_one_or_none()

        anomalies = await service.detect_listing_anomalies(
            db=db_session,
            listing_id=listing_id,
            lookback_days=30,
        )

        # Should detect CTR drop (60% decline > 30% threshold)
        ctr_anomalies = [a for a in anomalies if a["type"] == "ctr_drop"]
        assert len(ctr_anomalies) >= 1

        anomaly = ctr_anomalies[0]
        assert anomaly["severity"] in ["critical", "high", "medium", "low"]
        assert "decline_percentage" in anomaly["details"]
        assert anomaly["details"]["decline_percentage"] >= 30.0

    @pytest.mark.asyncio
    async def test_detect_cvr_drop_anomaly(
        self, db_session: AsyncSession, listing_performance_data
    ):
        """Test CVR drop detection when conversion rate declines significantly."""
        service = AnomalyDetectionService()
        listing_id = listing_performance_data["listing_id"]

        anomalies = await service.detect_listing_anomalies(
            db=db_session,
            listing_id=listing_id,
            lookback_days=30,
        )

        # Should detect CVR drop (50% decline > 30% threshold)
        cvr_anomalies = [a for a in anomalies if a["type"] == "cvr_drop"]
        assert len(cvr_anomalies) >= 1

        anomaly = cvr_anomalies[0]
        assert anomaly["severity"] in ["critical", "high", "medium", "low"]
        assert "decline_percentage" in anomaly["details"]

    @pytest.mark.asyncio
    async def test_no_ctr_drop_when_stable(self, db_session: AsyncSession, sample_platform_listing):
        """Test no CTR drop anomaly when CTR is stable."""
        today = date.today()

        # Create stable CTR data
        for i in range(14):
            perf = ListingPerformanceDaily(
                id=uuid4(),
                listing_id=sample_platform_listing.id,
                metric_date=today - timedelta(days=i),
                impressions=1000,
                clicks=50,  # Stable 5% CTR
                orders=5,   # Stable 10% CVR
            )
            db_session.add(perf)

        await db_session.commit()

        service = AnomalyDetectionService()
        anomalies = await service.detect_listing_anomalies(
            db=db_session,
            listing_id=sample_platform_listing.id,
            lookback_days=30,
        )

        ctr_anomalies = [a for a in anomalies if a["type"] == "ctr_drop"]
        assert len(ctr_anomalies) == 0


class TestDetectSupplierAnomalies:
    """Tests for supplier-specific anomaly detection."""

    @pytest.mark.asyncio
    async def test_detect_supplier_anomalies_no_data(self, db_session: AsyncSession):
        """Test with no supplier data returns empty anomalies."""
        service = AnomalyDetectionService()
        supplier_id = uuid4()

        anomalies = await service.detect_supplier_anomalies(
            db=db_session,
            supplier_id=supplier_id,
        )

        assert isinstance(anomalies, list)
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_detect_supplier_delay_anomaly(
        self, db_session: AsyncSession, sample_supplier
    ):
        """Test supplier delay detection with overdue purchase orders."""
        # Create overdue purchase order
        threshold_date = datetime.utcnow() - timedelta(days=15)

        order = PurchaseOrder(
            id=uuid4(),
            supplier_id=sample_supplier.id,
            po_number=f"PO-DELAY-{uuid4().hex[:8]}",
            status=PurchaseOrderStatus.SUBMITTED,
            order_date=threshold_date,  # 15 days ago (> 14 day threshold)
            total_amount=Decimal("1000.00"),
            currency="USD",
        )
        db_session.add(order)
        await db_session.commit()

        service = AnomalyDetectionService()
        anomalies = await service.detect_supplier_anomalies(
            db=db_session,
            supplier_id=sample_supplier.id,
        )

        delay_anomalies = [a for a in anomalies if a["type"] == "supplier_delay"]
        assert len(delay_anomalies) >= 1

        anomaly = delay_anomalies[0]
        assert anomaly["severity"] in ["critical", "high"]
        assert "delayed_orders" in anomaly["details"]
        assert anomaly["details"]["delayed_orders"] >= 1

    @pytest.mark.asyncio
    async def test_detect_supplier_fulfillment_issues(
        self, db_session: AsyncSession, sample_supplier, sample_product_variant
    ):
        """Test supplier fulfillment issues detection with high refunds."""
        # Create supplier offer linking to variant
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

        # Create multiple refund cases for this variant
        today = date.today()
        for i in range(6):
            order = PlatformOrder(
                id=uuid4(),
                platform=TargetPlatform.TEMU,
                region="US",
                platform_order_id=f"ORDER-FULFILL-{i}",
                idempotency_key=f"IDEMPOTENCY-FULFILL-{i}",
                order_status=OrderStatus.REFUNDED,
                currency="USD",
                total_amount=Decimal("50.00"),
                ordered_at=datetime.utcnow() - timedelta(days=i),
            )
            db_session.add(order)
            await db_session.flush()

            refund = RefundCase(
                id=uuid4(),
                platform_order_id=order.id,
                product_variant_id=sample_product_variant.id,
                refund_amount=Decimal("15.00"),
                currency="USD",
                refund_reason=RefundReason.QUALITY_ISSUE,
                refund_status=RefundStatus.APPROVED,
                requested_at=datetime.utcnow() - timedelta(days=i),
            )
            db_session.add(refund)

        await db_session.commit()

        service = AnomalyDetectionService()
        anomalies = await service.detect_supplier_anomalies(
            db=db_session,
            supplier_id=sample_supplier.id,
        )

        fulfillment_anomalies = [a for a in anomalies if a["type"] == "supplier_fulfillment_issues"]
        assert len(fulfillment_anomalies) >= 1

        anomaly = fulfillment_anomalies[0]
        assert anomaly["severity"] == "high"
        assert "refund_count" in anomaly["details"]


class TestDetectGlobalAnomalies:
    """Tests for global anomaly detection."""

    @pytest.mark.asyncio
    async def test_detect_global_anomalies_empty(self, db_session: AsyncSession):
        """Test global anomaly detection with no data."""
        service = AnomalyDetectionService()

        result = await service.detect_global_anomalies(
            db=db_session,
            lookback_days=30,
            limit=100,
        )

        assert "total_anomalies" in result
        assert "affected_skus" in result
        assert "by_type" in result
        assert "by_severity" in result
        assert "anomalies" in result
        assert result["total_anomalies"] == 0
        assert result["affected_skus"] == 0

    @pytest.mark.asyncio
    async def test_detect_global_anomalies_with_data(
        self, db_session: AsyncSession, profit_ledger_data, inventory_data, sample_candidate
    ):
        """Test global anomaly detection aggregates anomalies correctly."""
        service = AnomalyDetectionService()
        variant_id = profit_ledger_data["variant_id"]

        # Create an active listing linked to the variant
        listing = PlatformListing(
            id=uuid4(),
            candidate_product_id=sample_candidate.id,
            product_variant_id=variant_id,
            platform=TargetPlatform.TEMU,
            region="US",
            status=PlatformListingStatus.ACTIVE,
            price=Decimal("50.00"),
            currency="USD",
        )
        db_session.add(listing)
        await db_session.commit()

        result = await service.detect_global_anomalies(
            db=db_session,
            lookback_days=30,
            limit=100,
        )

        assert result["total_anomalies"] >= 1
        assert result["affected_skus"] >= 1
        assert "by_severity" in result
        assert isinstance(result["anomalies"], list)


class TestSaveAnomalySignal:
    """Tests for save_anomaly_signal method."""

    @pytest.mark.asyncio
    async def test_save_anomaly_signal(self, db_session: AsyncSession, sample_product_variant):
        """Test saving anomaly signal to database."""
        service = AnomalyDetectionService()

        signal = await service.save_anomaly_signal(
            db=db_session,
            target_type="product_variant",
            target_id=sample_product_variant.id,
            anomaly_type="sales_drop",
            severity="high",
            anomaly_data={
                "decline_percentage": 45.0,
                "recent_revenue": 350.0,
                "prior_revenue": 700.0,
            },
            description="Sales dropped 45% in the last 7 days",
        )

        assert signal.id is not None
        assert signal.target_type == "product_variant"
        assert signal.target_id == sample_product_variant.id
        assert signal.anomaly_type == "sales_drop"
        assert signal.severity == "high"
        assert signal.is_resolved is False

    @pytest.mark.asyncio
    async def test_save_anomaly_signal_with_resolution(
        self, db_session: AsyncSession, sample_product_variant
    ):
        """Test saving anomaly signal with resolution status."""
        service = AnomalyDetectionService()

        signal = await service.save_anomaly_signal(
            db=db_session,
            target_type="product_variant",
            target_id=sample_product_variant.id,
            anomaly_type="margin_collapse",
            severity="critical",
            anomaly_data={
                "average_margin": 8.0,
                "threshold": 15.0,
            },
            description="Margin collapsed below threshold",
        )

        # Manually resolve
        signal.is_resolved = True
        signal.resolved_at = datetime.utcnow()
        signal.resolved_by = "test_user"
        signal.resolution_notes = "Price adjustment applied"
        await db_session.commit()

        assert signal.is_resolved is True
        assert signal.resolved_by == "test_user"


class TestCalculateSeverity:
    """Tests for severity calculation."""

    def test_calculate_severity_critical(self):
        """Test critical severity when value is 2x threshold."""
        service = AnomalyDetectionService()
        severity = service._calculate_severity(
            value=Decimal("0.60"),  # 60% decline
            threshold=Decimal("0.30"),  # 30% threshold
        )
        assert severity == "critical"

    def test_calculate_severity_high(self):
        """Test high severity when value is 1.5x threshold."""
        service = AnomalyDetectionService()
        severity = service._calculate_severity(
            value=Decimal("0.45"),  # 45% decline
            threshold=Decimal("0.30"),  # 30% threshold
        )
        assert severity == "high"

    def test_calculate_severity_medium(self):
        """Test medium severity when value is 1.2x threshold."""
        service = AnomalyDetectionService()
        severity = service._calculate_severity(
            value=Decimal("0.36"),  # 36% decline
            threshold=Decimal("0.30"),  # 30% threshold
        )
        assert severity == "medium"

    def test_calculate_severity_low(self):
        """Test low severity when value is just above threshold."""
        service = AnomalyDetectionService()
        severity = service._calculate_severity(
            value=Decimal("0.31"),  # 31% decline
            threshold=Decimal("0.30"),  # 30% threshold
        )
        assert severity == "low"
