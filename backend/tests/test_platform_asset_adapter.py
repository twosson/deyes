"""Tests for PlatformAssetAdapter."""
import pytest
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.platform_asset_adapter import PlatformAssetAdapter


async def _create_variant(db_session: AsyncSession) -> ProductVariant:
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
    return variant, candidate


@pytest.mark.asyncio
async def test_get_platform_rule(db_session: AsyncSession):
    """Should retrieve platform content rule."""
    # Platform rules are seeded in migration
    adapter = PlatformAssetAdapter()
    rule = await adapter.get_platform_rule(
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        db=db_session,
    )

    assert rule is not None
    assert rule.platform == TargetPlatform.AMAZON
    assert rule.asset_type == AssetType.MAIN_IMAGE
    assert rule.allow_text_on_image is False
    assert rule.image_spec["width"] == 1000
    assert rule.image_spec["height"] == 1000


@pytest.mark.asyncio
async def test_validate_asset_compliance_pass(db_session: AsyncSession):
    """Should validate compliant asset."""
    variant, candidate = await _create_variant(db_session)
    await db_session.commit()

    # Create compliant asset
    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset.jpg",
        usage_scope=ContentUsageScope.BASE,
        spec={
            "width": 1000,
            "height": 1000,
            "format": "jpg",
            "has_text": False,
        },
        language_tags=["en"],
        compliance_tags=["amazon_compliant"],
    )
    db_session.add(asset)
    await db_session.commit()

    adapter = PlatformAssetAdapter()
    validation = await adapter.validate_asset_compliance(
        asset=asset,
        platform=TargetPlatform.AMAZON,
        db=db_session,
    )

    assert validation["valid"] is True
    assert len(validation["violations"]) == 0


@pytest.mark.asyncio
async def test_validate_asset_compliance_text_violation(db_session: AsyncSession):
    """Should detect text on image violation."""
    variant, candidate = await _create_variant(db_session)
    await db_session.commit()

    # Create asset with text (violates Amazon rule)
    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset.jpg",
        spec={
            "width": 1000,
            "height": 1000,
            "format": "jpg",
            "has_text": True,
        },
    )
    db_session.add(asset)
    await db_session.commit()

    adapter = PlatformAssetAdapter()
    validation = await adapter.validate_asset_compliance(
        asset=asset,
        platform=TargetPlatform.AMAZON,
        db=db_session,
    )

    assert validation["valid"] is False
    assert "text_not_allowed" in validation["violations"]
    assert "regenerate_without_text" in validation["suggestions"]


@pytest.mark.asyncio
async def test_validate_asset_compliance_dimension_mismatch(db_session: AsyncSession):
    """Should detect dimension mismatch."""
    variant, candidate = await _create_variant(db_session)
    await db_session.commit()

    # Create asset with wrong dimensions
    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset.jpg",
        spec={
            "width": 800,
            "height": 800,
            "format": "jpg",
            "has_text": False,
        },
    )
    db_session.add(asset)
    await db_session.commit()

    adapter = PlatformAssetAdapter()
    validation = await adapter.validate_asset_compliance(
        asset=asset,
        platform=TargetPlatform.AMAZON,
        db=db_session,
    )

    assert validation["valid"] is False
    assert "dimension_mismatch" in validation["violations"]


@pytest.mark.asyncio
async def test_suggest_asset_derivation(db_session: AsyncSession):
    """Should suggest derivation actions."""
    variant, candidate = await _create_variant(db_session)
    await db_session.commit()

    # Create base asset
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.jpg",
        usage_scope=ContentUsageScope.BASE,
        spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
            "has_text": False,
        },
    )
    db_session.add(base_asset)
    await db_session.commit()

    adapter = PlatformAssetAdapter()
    suggestion = await adapter.suggest_asset_derivation(
        base_asset=base_asset,
        platform=TargetPlatform.AMAZON,
        db=db_session,
    )

    assert suggestion["base_asset_id"] == str(base_asset.id)
    assert suggestion["platform"] == "amazon"
    assert suggestion["usage_scope"] == "platform_derived"
    assert "resize" in suggestion["actions"] or "convert_format" in suggestion["actions"]


@pytest.mark.asyncio
async def test_select_best_asset_prioritizes_platform_derived(db_session: AsyncSession):
    """Should prioritize platform-derived assets."""
    variant, candidate = await _create_variant(db_session)
    await db_session.commit()

    # Create base asset
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.jpg",
        usage_scope=ContentUsageScope.BASE,
    )
    db_session.add(base_asset)

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
    )
    db_session.add(derived_asset)
    await db_session.commit()

    adapter = PlatformAssetAdapter()
    selected = await adapter.select_best_asset(
        variant_id=variant.id,
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        db=db_session,
    )

    assert selected is not None
    assert selected.id == derived_asset.id


@pytest.mark.asyncio
async def test_select_best_asset_falls_back_to_base(db_session: AsyncSession):
    """Should fall back to base asset if no platform-derived exists."""
    variant, candidate = await _create_variant(db_session)
    await db_session.commit()

    # Create only base asset
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.jpg",
        usage_scope=ContentUsageScope.BASE,
    )
    db_session.add(base_asset)
    await db_session.commit()

    adapter = PlatformAssetAdapter()
    selected = await adapter.select_best_asset(
        variant_id=variant.id,
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        db=db_session,
    )

    assert selected is not None
    assert selected.id == base_asset.id


@pytest.mark.asyncio
async def test_select_best_asset_prioritizes_localized(db_session: AsyncSession):
    """Should prioritize LOCALIZED assets over PLATFORM_DERIVED."""
    variant, candidate = await _create_variant(db_session)
    await db_session.commit()

    # Create base asset
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.jpg",
        usage_scope=ContentUsageScope.BASE,
    )
    db_session.add(base_asset)

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
    )
    db_session.add(derived_asset)

    # Create localized asset
    localized_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/amazon_en.jpg",
        usage_scope=ContentUsageScope.LOCALIZED,
        platform_tags=["amazon"],
        language_tags=["en"],
        parent_asset_id=base_asset.id,
    )
    db_session.add(localized_asset)
    await db_session.commit()

    adapter = PlatformAssetAdapter()
    selected = await adapter.select_best_asset(
        variant_id=variant.id,
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        db=db_session,
        language="en",
    )

    # Should select LOCALIZED asset
    assert selected is not None
    assert selected.id == localized_asset.id
    assert selected.usage_scope == ContentUsageScope.LOCALIZED


@pytest.mark.asyncio
async def test_select_best_asset_localized_language_only(db_session: AsyncSession):
    """Should select LOCALIZED asset with language match even without platform match."""
    variant, candidate = await _create_variant(db_session)
    await db_session.commit()

    # Create base asset
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.jpg",
        usage_scope=ContentUsageScope.BASE,
    )
    db_session.add(base_asset)

    # Create localized asset with language but different platform
    localized_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/temu_en.jpg",
        usage_scope=ContentUsageScope.LOCALIZED,
        platform_tags=["temu"],
        language_tags=["en"],
        parent_asset_id=base_asset.id,
    )
    db_session.add(localized_asset)
    await db_session.commit()

    adapter = PlatformAssetAdapter()
    selected = await adapter.select_best_asset(
        variant_id=variant.id,
        platform=TargetPlatform.AMAZON,  # Different platform
        asset_type=AssetType.MAIN_IMAGE,
        db=db_session,
        language="en",
    )

    # Should select LOCALIZED asset based on language match
    # (Priority 3: language-only match)
    assert selected is not None
    assert selected.id == localized_asset.id

