"""Tests for listing activation service."""
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CandidateStatus,
    InventoryMode,
    PlatformListingStatus,
    ProductMasterStatus,
    ProductVariantStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    PlatformListing,
    ProductMaster,
    ProductVariant,
    StrategyRun,
    Supplier,
    SupplierOffer,
)
from app.services.inventory_allocator import InventoryAllocator
from app.services.listing_activation_service import ListingActivationService


@pytest_asyncio.fixture
async def sample_strategy_run(db_session):
    """Create a sample strategy run."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()
    return strategy_run


@pytest_asyncio.fixture
async def sample_candidate(db_session, sample_strategy_run):
    """Create a sample candidate."""
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=sample_strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Test Product",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


@pytest_asyncio.fixture
async def sample_variant_pre_order(db_session, sample_candidate):
    """Create a sample variant in pre-order mode."""
    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        internal_sku="SKU-PREORDER-001",
        name="Pre-order Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-PREORDER-001",
        attributes={},
        inventory_mode=InventoryMode.PRE_ORDER,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(variant)
    return variant


@pytest_asyncio.fixture
async def sample_variant_stock_first(db_session, sample_candidate):
    """Create a sample variant in stock-first mode."""
    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        internal_sku="SKU-STOCK-001",
        name="Stock-first Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-STOCK-001",
        attributes={},
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(variant)
    return variant


@pytest.mark.asyncio
async def test_pre_order_mode_eligible_with_supplier_offer(
    db_session, sample_candidate, sample_variant_pre_order
):
    """Pre-order mode should be eligible with supplier offer and 0 inventory."""
    # Create supplier and offer
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
        variant_id=sample_variant_pre_order.id,
        unit_price=Decimal("10.00"),
        currency="USD",
        moq=100,
        lead_time_days=30,
    )
    db_session.add(offer)
    await db_session.commit()

    # Create listing
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        product_variant_id=sample_variant_pre_order.id,
        inventory_mode=InventoryMode.PRE_ORDER,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        inventory=0,
        status=PlatformListingStatus.DRAFT,
    )
    db_session.add(listing)
    await db_session.commit()

    # Check eligibility
    service = ListingActivationService()
    eligibility = await service.check_activation_eligibility(db_session, listing.id)

    assert eligibility.eligible is True
    assert eligibility.reason is None
    assert eligibility.inventory_mode == InventoryMode.PRE_ORDER
    assert eligibility.available_quantity == 0
    assert eligibility.min_inventory_required == 0
    assert eligibility.has_supplier_offer is True


@pytest.mark.asyncio
async def test_pre_order_mode_ineligible_without_supplier_offer(
    db_session, sample_candidate, sample_variant_pre_order
):
    """Pre-order mode should be ineligible without supplier offer."""
    # Create listing without supplier offer
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        product_variant_id=sample_variant_pre_order.id,
        inventory_mode=InventoryMode.PRE_ORDER,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        inventory=0,
        status=PlatformListingStatus.DRAFT,
    )
    db_session.add(listing)
    await db_session.commit()

    # Check eligibility
    service = ListingActivationService()
    eligibility = await service.check_activation_eligibility(db_session, listing.id)

    assert eligibility.eligible is False
    assert eligibility.reason == "no_supplier_offer"
    assert eligibility.inventory_mode == InventoryMode.PRE_ORDER
    assert eligibility.has_supplier_offer is False


@pytest.mark.asyncio
async def test_stock_first_mode_eligible_with_sufficient_inventory(
    db_session, sample_candidate, sample_variant_stock_first
):
    """Stock-first mode should be eligible with sufficient inventory."""
    # Add inventory (Temu threshold is 10)
    allocator = InventoryAllocator()
    await allocator.record_inbound(db_session, sample_variant_stock_first.id, quantity=50)

    # Create listing
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        product_variant_id=sample_variant_stock_first.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        inventory=50,
        status=PlatformListingStatus.DRAFT,
    )
    db_session.add(listing)
    await db_session.commit()

    # Check eligibility
    service = ListingActivationService()
    eligibility = await service.check_activation_eligibility(db_session, listing.id)

    assert eligibility.eligible is True
    assert eligibility.reason is None
    assert eligibility.inventory_mode == InventoryMode.STOCK_FIRST
    assert eligibility.available_quantity == 50
    assert eligibility.min_inventory_required == 10


@pytest.mark.asyncio
async def test_stock_first_mode_ineligible_with_insufficient_inventory(
    db_session, sample_candidate, sample_variant_stock_first
):
    """Stock-first mode should be ineligible with insufficient inventory."""
    # Add only 5 units (Temu threshold is 10)
    allocator = InventoryAllocator()
    await allocator.record_inbound(db_session, sample_variant_stock_first.id, quantity=5)

    # Create listing
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        product_variant_id=sample_variant_stock_first.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        inventory=5,
        status=PlatformListingStatus.DRAFT,
    )
    db_session.add(listing)
    await db_session.commit()

    # Check eligibility
    service = ListingActivationService()
    eligibility = await service.check_activation_eligibility(db_session, listing.id)

    assert eligibility.eligible is False
    assert "insufficient_inventory" in eligibility.reason
    assert eligibility.inventory_mode == InventoryMode.STOCK_FIRST
    assert eligibility.available_quantity == 5
    assert eligibility.min_inventory_required == 10


@pytest.mark.asyncio
async def test_platform_specific_thresholds(db_session, sample_candidate, sample_variant_stock_first):
    """Test platform-specific inventory thresholds."""
    allocator = InventoryAllocator()

    # Test Amazon (threshold 50)
    await allocator.record_inbound(db_session, sample_variant_stock_first.id, quantity=45)

    listing_amazon = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        product_variant_id=sample_variant_stock_first.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.AMAZON,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        inventory=45,
        status=PlatformListingStatus.DRAFT,
    )
    db_session.add(listing_amazon)
    await db_session.commit()

    service = ListingActivationService()
    eligibility = await service.check_activation_eligibility(db_session, listing_amazon.id)

    assert eligibility.eligible is False
    assert eligibility.min_inventory_required == 50
    assert eligibility.available_quantity == 45

    # Add more inventory to meet threshold
    await allocator.record_inbound(db_session, sample_variant_stock_first.id, quantity=10)

    eligibility = await service.check_activation_eligibility(db_session, listing_amazon.id)
    assert eligibility.eligible is True
    assert eligibility.available_quantity == 55


@pytest.mark.asyncio
async def test_activate_listing_if_eligible_success(
    db_session, sample_candidate, sample_variant_pre_order
):
    """Test activate_listing_if_eligible activates eligible listing."""
    # Create supplier and offer
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
        variant_id=sample_variant_pre_order.id,
        unit_price=Decimal("10.00"),
        currency="USD",
        moq=100,
        lead_time_days=30,
    )
    db_session.add(offer)
    await db_session.commit()

    # Create listing
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        product_variant_id=sample_variant_pre_order.id,
        inventory_mode=InventoryMode.PRE_ORDER,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        inventory=0,
        status=PlatformListingStatus.DRAFT,
    )
    db_session.add(listing)
    await db_session.commit()

    # Activate listing
    service = ListingActivationService()
    activated, reason = await service.activate_listing_if_eligible(db_session, listing.id)

    assert activated is True
    assert reason is None

    # Verify status updated
    await db_session.refresh(listing)
    assert listing.status == PlatformListingStatus.ACTIVE


@pytest.mark.asyncio
async def test_activate_listing_if_eligible_failure(
    db_session, sample_candidate, sample_variant_pre_order
):
    """Test activate_listing_if_eligible fails for ineligible listing."""
    # Create listing without supplier offer
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        product_variant_id=sample_variant_pre_order.id,
        inventory_mode=InventoryMode.PRE_ORDER,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        inventory=0,
        status=PlatformListingStatus.DRAFT,
    )
    db_session.add(listing)
    await db_session.commit()

    # Try to activate listing
    service = ListingActivationService()
    activated, reason = await service.activate_listing_if_eligible(db_session, listing.id)

    assert activated is False
    assert reason == "no_supplier_offer"

    # Verify status not updated
    await db_session.refresh(listing)
    assert listing.status == PlatformListingStatus.DRAFT
