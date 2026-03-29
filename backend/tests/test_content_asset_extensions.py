"""Tests for ContentAsset Phase2 extensions."""
import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AssetType, ContentUsageScope, SourcePlatform, StrategyRunStatus, TriggerType
from app.db.models import CandidateProduct, ContentAsset, StrategyRun


async def _create_strategy_run(db_session: AsyncSession) -> StrategyRun:
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


async def _create_candidate(
    db_session: AsyncSession,
    strategy_run_id,
    *,
    title: str = "Test Product",
) -> CandidateProduct:
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run_id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title=title,
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


@pytest.mark.asyncio
async def test_content_asset_with_usage_scope(db_session: AsyncSession):
    """ContentAsset should support usage_scope field."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    # Create base asset
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.jpg",
        usage_scope=ContentUsageScope.BASE,
        spec={"width": 1024, "height": 1024, "format": "jpg", "has_text": False},
    )
    db_session.add(base_asset)
    await db_session.commit()

    # Verify
    await db_session.refresh(base_asset)
    assert base_asset.usage_scope == ContentUsageScope.BASE
    assert base_asset.spec["has_text"] is False


@pytest.mark.asyncio
async def test_content_asset_with_language_tags(db_session: AsyncSession):
    """ContentAsset should support language_tags field."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset.jpg",
        language_tags=["en", "zh", "ja"],
    )
    db_session.add(asset)
    await db_session.commit()

    await db_session.refresh(asset)
    assert asset.language_tags == ["en", "zh", "ja"]


@pytest.mark.asyncio
async def test_content_asset_with_compliance_tags(db_session: AsyncSession):
    """ContentAsset should support compliance_tags field."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset.jpg",
        compliance_tags=["amazon_compliant", "temu_compliant"],
    )
    db_session.add(asset)
    await db_session.commit()

    await db_session.refresh(asset)
    assert "amazon_compliant" in asset.compliance_tags
    assert "temu_compliant" in asset.compliance_tags


@pytest.mark.asyncio
async def test_content_asset_parent_child_relationship(db_session: AsyncSession):
    """ContentAsset should support parent-child derivation."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    # Create base asset
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.jpg",
        usage_scope=ContentUsageScope.BASE,
    )
    db_session.add(base_asset)
    await db_session.flush()

    # Create derived asset
    derived_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/derived.jpg",
        usage_scope=ContentUsageScope.PLATFORM_DERIVED,
        parent_asset_id=base_asset.id,
        platform_tags=["amazon"],
    )
    db_session.add(derived_asset)
    await db_session.commit()

    # Verify parent-child relationship
    await db_session.refresh(base_asset)
    await db_session.refresh(derived_asset)

    assert derived_asset.parent_asset_id == base_asset.id
    assert len(base_asset.derived_assets) == 1
    assert base_asset.derived_assets[0].id == derived_asset.id


@pytest.mark.asyncio
async def test_query_assets_by_usage_scope(db_session: AsyncSession):
    """Should be able to query assets by usage_scope."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    # Create base and derived assets
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.jpg",
        usage_scope=ContentUsageScope.BASE,
    )
    derived_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/derived.jpg",
        usage_scope=ContentUsageScope.PLATFORM_DERIVED,
        parent_asset_id=base_asset.id,
    )
    db_session.add(base_asset)
    db_session.add(derived_asset)
    await db_session.commit()

    # Query base assets
    base_stmt = select(ContentAsset).where(
        ContentAsset.candidate_product_id == candidate.id,
        ContentAsset.usage_scope == ContentUsageScope.BASE,
    )
    base_result = await db_session.execute(base_stmt)
    base_assets = list(base_result.scalars().all())

    assert len(base_assets) == 1
    assert base_assets[0].id == base_asset.id

    # Query derived assets
    derived_stmt = select(ContentAsset).where(
        ContentAsset.candidate_product_id == candidate.id,
        ContentAsset.usage_scope == ContentUsageScope.PLATFORM_DERIVED,
    )
    derived_result = await db_session.execute(derived_stmt)
    derived_assets = list(derived_result.scalars().all())

    assert len(derived_assets) == 1
    assert derived_assets[0].id == derived_asset.id
