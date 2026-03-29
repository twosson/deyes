"""Tests for PlatformPublisherAgent asset selection integration."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext
from app.agents.platform_publisher import PlatformPublisherAgent
from app.core.enums import (
    AssetType,
    CandidateStatus,
    ContentUsageScope,
    InventoryMode,
    ProductLifecycle,
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
    PlatformContentRule,
    ProductMaster,
    ProductVariant,
    StrategyRun,
)


async def _create_variant_with_assets(
    db_session: AsyncSession,
) -> tuple[ProductVariant, CandidateProduct, ContentAsset, ContentAsset]:
    """Create variant with base and derived assets."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Test Product",
        status=CandidateStatus.DISCOVERED,
        lifecycle_status=ProductLifecycle.READY_TO_PUBLISH,
        platform_price=Decimal("10.00"),
    )
    db_session.add(candidate)
    await db_session.flush()

    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=candidate.id,
        internal_sku="SKU-TEST-001",
        name="Test Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-TEST-001",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.flush()

    # Create base asset
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.png",
        usage_scope=ContentUsageScope.BASE,
        human_approved=True,
        spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
            "has_text": False,
        },
    )
    db_session.add(base_asset)
    await db_session.flush()

    # Create platform-derived asset
    derived_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/amazon.jpg",
        usage_scope=ContentUsageScope.PLATFORM_DERIVED,
        platform_tags=["amazon"],
        parent_asset_id=base_asset.id,
        human_approved=True,
        spec={
            "width": 1000,
            "height": 1000,
            "format": "jpg",
            "has_text": False,
        },
    )
    db_session.add(derived_asset)
    await db_session.flush()

    return variant, candidate, base_asset, derived_asset


@pytest.mark.asyncio
async def test_select_platform_assets_prioritizes_derived(db_session: AsyncSession):
    """Should prioritize platform-derived assets over base assets."""
    variant, candidate, base_asset, derived_asset = await _create_variant_with_assets(
        db_session
    )

    # Create platform rule
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1000,
            "height": 1000,
            "format": "jpg",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Create agent
    agent = PlatformPublisherAgent()

    # Create context
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={},
    )

    # Select assets
    selected_assets = await agent._select_platform_assets(
        variant_id=variant.id,
        candidate=candidate,
        platform=TargetPlatform.AMAZON,
        region="us",
        fallback_assets=[base_asset, derived_asset],
        context=context,
    )

    # Should select derived asset
    assert len(selected_assets) == 1
    assert selected_assets[0].id == derived_asset.id
    assert selected_assets[0].usage_scope == ContentUsageScope.PLATFORM_DERIVED


@pytest.mark.asyncio
async def test_select_platform_assets_falls_back_to_base(db_session: AsyncSession):
    """Should fall back to base asset if no derived asset exists."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Test Product",
        status=CandidateStatus.DISCOVERED,
        lifecycle_status=ProductLifecycle.READY_TO_PUBLISH,
        platform_price=Decimal("10.00"),
    )
    db_session.add(candidate)
    await db_session.flush()

    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=candidate.id,
        internal_sku="SKU-TEST-002",
        name="Test Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-TEST-002",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.flush()

    # Create only base asset (compliant)
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.jpg",
        usage_scope=ContentUsageScope.BASE,
        human_approved=True,
        spec={
            "width": 1000,
            "height": 1000,
            "format": "jpg",
            "has_text": False,
        },
    )
    db_session.add(base_asset)

    # Create platform rule (matches base asset)
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1000,
            "height": 1000,
            "format": "jpg",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Create agent
    agent = PlatformPublisherAgent()

    # Create context
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={},
    )

    # Select assets
    selected_assets = await agent._select_platform_assets(
        variant_id=variant.id,
        candidate=candidate,
        platform=TargetPlatform.AMAZON,
        region="us",
        fallback_assets=[base_asset],
        context=context,
    )

    # Should select base asset
    assert len(selected_assets) == 1
    assert selected_assets[0].id == base_asset.id
    assert selected_assets[0].usage_scope == ContentUsageScope.BASE


@pytest.mark.asyncio
async def test_select_platform_assets_no_variant_fallback(db_session: AsyncSession):
    """Should fall back to legacy filter when no variant exists."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Test Product",
        status=CandidateStatus.DISCOVERED,
        lifecycle_status=ProductLifecycle.READY_TO_PUBLISH,
        platform_price=Decimal("10.00"),
    )
    db_session.add(candidate)
    await db_session.flush()

    # Create asset without variant
    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset.jpg",
        human_approved=True,
    )
    db_session.add(asset)
    await db_session.commit()

    # Create agent
    agent = PlatformPublisherAgent()

    # Create context
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={},
    )

    # Select assets (no variant_id)
    selected_assets = await agent._select_platform_assets(
        variant_id=None,
        candidate=candidate,
        platform=TargetPlatform.AMAZON,
        region="us",
        fallback_assets=[asset],
        context=context,
    )

    # Should fall back to legacy filter
    assert len(selected_assets) >= 1


@pytest.mark.asyncio
async def test_infer_language_from_region():
    """Should infer correct language from region."""
    agent = PlatformPublisherAgent()

    assert agent._infer_language_from_region("us") == "en"
    assert agent._infer_language_from_region("uk") == "en"
    assert agent._infer_language_from_region("de") == "de"
    assert agent._infer_language_from_region("fr") == "fr"
    assert agent._infer_language_from_region("jp") == "ja"
    assert agent._infer_language_from_region("cn") == "zh"
    assert agent._infer_language_from_region("unknown") == "en"  # Default


@pytest.mark.asyncio
async def test_resolve_variant_id(db_session: AsyncSession):
    """Should resolve variant_id from candidate."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Test Product",
    )
    db_session.add(candidate)
    await db_session.flush()

    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=candidate.id,
        internal_sku="SKU-TEST-003",
        name="Test Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-TEST-003",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.commit()

    # Create agent
    agent = PlatformPublisherAgent()

    # Resolve variant_id
    resolved_id = await agent._resolve_variant_id(candidate, db_session)

    assert resolved_id == variant.id


@pytest.mark.asyncio
async def test_resolve_variant_id_not_found(db_session: AsyncSession):
    """Should return None when variant not found."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Test Product",
    )
    db_session.add(candidate)
    await db_session.commit()

    # No master/variant created

    # Create agent
    agent = PlatformPublisherAgent()

    # Resolve variant_id
    resolved_id = await agent._resolve_variant_id(candidate, db_session)

    assert resolved_id is None
