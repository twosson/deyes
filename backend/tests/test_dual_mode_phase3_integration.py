"""Phase 3 dual-mode integration tests.

Tests same SKU publishing to multiple platforms with different inventory modes.
"""
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext
from app.agents.platform_publisher import PlatformPublisherAgent
from app.core.enums import (
    AssetType,
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
    ContentAsset,
    PlatformListing,
    ProductMaster,
    ProductVariant,
    StrategyRun,
    Supplier,
    SupplierOffer,
)
from app.services.candidate_conversion_service import CandidateConversionService
from app.services.inventory_allocator import InventoryAllocator


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
        title="Dual Mode Test Product",
        status=CandidateStatus.DISCOVERED,
        platform_price=Decimal("10.00"),
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


@pytest_asyncio.fixture
async def sample_content_asset(db_session, sample_candidate):
    """Create a sample content asset."""
    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/test-image.jpg",
        human_approved=True,
    )
    db_session.add(asset)
    await db_session.flush()
    return asset


@pytest.mark.asyncio
async def test_same_sku_dual_platform_dual_mode(
    db_session: AsyncSession,
    sample_candidate,
    sample_content_asset,
):
    """Test same SKU published to Temu (pre_order) and Amazon (stock_first)."""
    # 1. Convert candidate to SKU with PRE_ORDER mode
    conversion_service = CandidateConversionService()
    result = await conversion_service.convert_candidate_to_master(
        candidate_id=sample_candidate.id,
        db=db_session,
        auto_link_supplier=False,
    )

    master_id = result.product_master_id
    variant_id = result.product_variant_id

    # Verify variant created with default STOCK_FIRST mode
    variant = await db_session.get(ProductVariant, variant_id)
    assert variant is not None
    assert variant.inventory_mode == InventoryMode.STOCK_FIRST  # Default

    # 2. Add supplier offer (for pre_order activation)
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
        variant_id=variant_id,
        unit_price=Decimal("10.00"),
        currency="USD",
        moq=100,
        lead_time_days=30,
    )
    db_session.add(offer)
    await db_session.commit()

    # 3. Publish to Temu (pre_order platform)
    publisher = PlatformPublisherAgent()
    context_temu = AgentContext(
        db=db_session,
        input_data={
            "candidate_product_id": str(sample_candidate.id),
            "target_platforms": [{"platform": "temu", "region": "us"}],
            "auto_approve": True,
        },
    )
    result_temu = await publisher.execute(context_temu)

    assert result_temu.success is True
    assert result_temu.output_data["published_count"] == 1

    # 4. Verify Temu listing
    temu_listing_id = result_temu.output_data["listing_ids"][0]
    temu_listing = await db_session.get(PlatformListing, temu_listing_id)

    assert temu_listing is not None
    assert temu_listing.platform == TargetPlatform.TEMU
    assert temu_listing.product_variant_id == variant_id
    assert temu_listing.inventory_mode == InventoryMode.PRE_ORDER  # Inferred from platform
    # Should activate with supplier offer even with 0 inventory
    assert temu_listing.status == PlatformListingStatus.ACTIVE

    # 5. Add inventory (for stock_first activation)
    allocator = InventoryAllocator()
    await allocator.record_inbound(db_session, variant_id, quantity=60)

    # 6. Publish to Amazon (stock_first platform)
    context_amazon = AgentContext(
        db=db_session,
        input_data={
            "candidate_product_id": str(sample_candidate.id),
            "target_platforms": [{"platform": "amazon", "region": "us"}],
            "auto_approve": True,
        },
    )
    result_amazon = await publisher.execute(context_amazon)

    assert result_amazon.success is True
    assert result_amazon.output_data["published_count"] == 1

    # 7. Verify Amazon listing
    amazon_listing_id = result_amazon.output_data["listing_ids"][0]
    amazon_listing = await db_session.get(PlatformListing, amazon_listing_id)

    assert amazon_listing is not None
    assert amazon_listing.platform == TargetPlatform.AMAZON
    assert amazon_listing.product_variant_id == variant_id
    assert amazon_listing.inventory_mode == InventoryMode.STOCK_FIRST  # Inferred from platform
    # Should activate with inventory >= 50 (Amazon threshold)
    assert amazon_listing.status == PlatformListingStatus.ACTIVE

    # 8. Verify both listings share same variant
    assert temu_listing.product_variant_id == amazon_listing.product_variant_id


@pytest.mark.asyncio
async def test_pre_order_activation_fails_without_supplier_offer(
    db_session: AsyncSession,
    sample_candidate,
    sample_content_asset,
):
    """Test pre_order listing cannot activate without supplier offer."""
    # 1. Convert candidate to SKU
    conversion_service = CandidateConversionService()
    result = await conversion_service.convert_candidate_to_master(
        candidate_id=sample_candidate.id,
        db=db_session,
        auto_link_supplier=False,
    )

    variant_id = result.product_variant_id

    # 2. Publish to Temu without supplier offer
    publisher = PlatformPublisherAgent()
    context = AgentContext(
        db=db_session,
        input_data={
            "candidate_product_id": str(sample_candidate.id),
            "target_platforms": [{"platform": "temu", "region": "us"}],
            "auto_approve": True,
        },
    )
    result_publish = await publisher.execute(context)

    assert result_publish.success is True
    assert result_publish.output_data["published_count"] == 1

    # 3. Verify listing created but not activated
    listing_id = result_publish.output_data["listing_ids"][0]
    listing = await db_session.get(PlatformListing, listing_id)

    assert listing is not None
    assert listing.status == PlatformListingStatus.PENDING  # Not activated
    assert listing.inventory_mode == InventoryMode.PRE_ORDER
    assert listing.product_variant_id == variant_id


@pytest.mark.asyncio
async def test_stock_first_activation_fails_insufficient_inventory(
    db_session: AsyncSession,
    sample_candidate,
    sample_content_asset,
):
    """Test stock_first listing cannot activate with insufficient inventory."""
    # 1. Convert candidate to SKU
    conversion_service = CandidateConversionService()
    result = await conversion_service.convert_candidate_to_master(
        candidate_id=sample_candidate.id,
        db=db_session,
        auto_link_supplier=False,
    )

    variant_id = result.product_variant_id

    # 2. Add insufficient inventory (< 50 for Amazon)
    allocator = InventoryAllocator()
    await allocator.record_inbound(db_session, variant_id, quantity=30)

    # 3. Publish to Amazon
    publisher = PlatformPublisherAgent()
    context = AgentContext(
        db=db_session,
        input_data={
            "candidate_product_id": str(sample_candidate.id),
            "target_platforms": [{"platform": "amazon", "region": "us"}],
            "auto_approve": True,
        },
    )
    result_publish = await publisher.execute(context)

    assert result_publish.success is True
    assert result_publish.output_data["published_count"] == 1

    # 4. Verify listing created but not activated
    listing_id = result_publish.output_data["listing_ids"][0]
    listing = await db_session.get(PlatformListing, listing_id)

    assert listing is not None
    assert listing.status == PlatformListingStatus.PENDING  # Not activated
    assert listing.inventory_mode == InventoryMode.STOCK_FIRST
    assert listing.product_variant_id == variant_id
