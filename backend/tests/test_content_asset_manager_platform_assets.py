"""Tests for ContentAssetManagerAgent.generate_platform_assets()."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext
from app.agents.content_asset_manager import ContentAssetManagerAgent
from app.core.enums import (
    AssetType,
    ContentUsageScope,
    InventoryMode,
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


async def _create_variant_with_base_asset(
    db_session: AsyncSession,
) -> tuple[ProductVariant, CandidateProduct, ContentAsset]:
    """Create variant with base asset."""
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
        spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
            "has_text": False,
        },
    )
    db_session.add(base_asset)
    await db_session.flush()

    return variant, candidate, base_asset


@pytest.mark.asyncio
async def test_generate_platform_assets_success(db_session: AsyncSession):
    """Should generate platform-derived assets."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

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
    agent = ContentAssetManagerAgent()

    # Create context
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "action": "generate_platform_assets",
            "variant_id": str(variant.id),
            "platform": "amazon",
            "asset_types": ["main_image"],
        },
    )

    # Execute
    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["assets_created"] >= 1
    assert result.output_data["platform"] == "amazon"
    assert result.output_data["usage_scope"] == "platform_derived"


@pytest.mark.asyncio
async def test_generate_platform_assets_idempotent(db_session: AsyncSession):
    """Should reuse existing derived assets."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create platform rule
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)

    # Create existing derived asset
    existing_derived = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/amazon.jpg",
        usage_scope=ContentUsageScope.PLATFORM_DERIVED,
        platform_tags=["amazon"],
        parent_asset_id=base_asset.id,
        spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
            "has_text": False,
        },
    )
    db_session.add(existing_derived)
    await db_session.commit()

    # Create agent
    agent = ContentAssetManagerAgent()

    # Create context
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "action": "generate_platform_assets",
            "variant_id": str(variant.id),
            "platform": "amazon",
            "asset_types": ["main_image"],
        },
    )

    # Execute
    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["assets_created"] == 1
    # Should reuse existing asset
    assert str(existing_derived.id) in result.output_data["asset_ids"]


@pytest.mark.asyncio
async def test_generate_platform_assets_no_base_asset(db_session: AsyncSession):
    """Should handle missing base asset gracefully."""
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
    await db_session.commit()

    # No base asset created

    # Create agent
    agent = ContentAssetManagerAgent()

    # Create context
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={
            "action": "generate_platform_assets",
            "variant_id": str(variant.id),
            "platform": "amazon",
            "asset_types": ["main_image"],
        },
    )

    # Execute
    result = await agent.execute(context)

    # Should succeed but create no assets
    assert result.success is True
    assert result.output_data["assets_created"] == 0


@pytest.mark.asyncio
async def test_generate_platform_assets_with_language(db_session: AsyncSession):
    """Should generate language-specific derived assets."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create platform rule
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Create agent
    agent = ContentAssetManagerAgent()

    # Create context with language
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "action": "generate_platform_assets",
            "variant_id": str(variant.id),
            "platform": "amazon",
            "asset_types": ["main_image"],
            "language": "en",
        },
    )

    # Execute
    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["assets_created"] >= 1


@pytest.mark.asyncio
async def test_generate_platform_assets_force_regenerate(db_session: AsyncSession):
    """Should regenerate when force_regenerate is True."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create platform rule
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)

    # Create existing derived asset
    existing_derived = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/amazon_old.jpg",
        usage_scope=ContentUsageScope.PLATFORM_DERIVED,
        platform_tags=["amazon"],
        parent_asset_id=base_asset.id,
    )
    db_session.add(existing_derived)
    await db_session.commit()

    # Create agent
    agent = ContentAssetManagerAgent()

    # Create context with force_regenerate
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "action": "generate_platform_assets",
            "variant_id": str(variant.id),
            "platform": "amazon",
            "asset_types": ["main_image"],
            "force_regenerate": True,
        },
    )

    # Execute
    result = await agent.execute(context)

    assert result.success is True
    # Should create new asset even though existing one exists
    assert result.output_data["assets_created"] >= 1
