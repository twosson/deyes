"""Tests for AB test manager agent."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ab_test_manager import ABTestManagerAgent
from app.agents.base.agent import AgentContext
from app.core.enums import (
    AssetType,
    CandidateStatus,
    PlatformListingStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    ContentAsset,
    Experiment,
    ListingAssetAssociation,
    PlatformListing,
    StrategyRun,
)
from app.services.asset_performance_service import AssetPerformanceService


async def _create_strategy_run(db_session: AsyncSession) -> StrategyRun:
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()
    return strategy_run


async def _create_candidate(db_session: AsyncSession, *, suffix: str) -> CandidateProduct:
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id=f"abtest-{suffix}",
        title=f"AB Test Product {suffix}",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


async def _create_asset(
    db_session: AsyncSession,
    *,
    candidate_id,
    variant_group: str | None,
    suffix: str,
) -> ContentAsset:
    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate_id,
        asset_type=AssetType.MAIN_IMAGE,
        variant_group=variant_group,
        file_url=f"https://example.com/{suffix}.png",
    )
    db_session.add(asset)
    await db_session.flush()
    return asset


async def _create_listing(
    db_session: AsyncSession,
    *,
    candidate_id,
    region: str,
    platform: TargetPlatform = TargetPlatform.TEMU,
) -> PlatformListing:
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate_id,
        platform=platform,
        region=region,
        price=Decimal("19.99"),
        currency="USD" if region == "us" else "GBP",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.flush()
    return listing


async def _record_asset_performance(
    db_session: AsyncSession,
    *,
    asset_id,
    listing_id,
    impressions: int,
    clicks: int,
    orders: int = 0,
    units_sold: int = 0,
    revenue: Decimal = Decimal("0.00"),
    usage_count: int = 0,
) -> None:
    service = AssetPerformanceService()
    await service.record_daily_performance(
        db_session,
        asset_id=asset_id,
        listing_id=listing_id,
        metric_date=date.today(),
        impressions=impressions,
        clicks=clicks,
        orders=orders,
        units_sold=units_sold,
        revenue=revenue,
        usage_count=usage_count,
    )


@pytest.mark.asyncio
async def test_create_and_activate_succeeds(db_session: AsyncSession):
    """ABTestManagerAgent should create and activate an experiment."""
    candidate = await _create_candidate(db_session, suffix="001")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="control", suffix="a")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="challenger", suffix="b")

    agent = ABTestManagerAgent()
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "operation": "create_and_activate",
            "candidate_product_id": str(candidate.id),
            "name": "CTR experiment",
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["operation"] == "create_and_activate"
    assert result.output_data["candidate_product_id"] == str(candidate.id)
    assert result.output_data["status"] == "active"
    assert result.output_data["metric_goal"] == "ctr"
    assert result.output_data["variant_count"] >= 2


@pytest.mark.asyncio
async def test_select_winner_returns_none_when_samples_insufficient(db_session: AsyncSession):
    """ABTestManagerAgent should succeed without winner when sample size is too small."""
    candidate = await _create_candidate(db_session, suffix="002")
    control = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="control", suffix="threshold-a"
    )
    challenger = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="challenger", suffix="threshold-b"
    )
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")

    await _record_asset_performance(
        db_session,
        asset_id=control.id,
        listing_id=listing.id,
        impressions=50,
        clicks=5,
    )
    await _record_asset_performance(
        db_session,
        asset_id=challenger.id,
        listing_id=listing.id,
        impressions=80,
        clicks=12,
    )

    agent = ABTestManagerAgent()
    create_context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "operation": "create_and_activate",
            "candidate_product_id": str(candidate.id),
        },
    )
    create_result = await agent.execute(create_context)
    experiment_id = create_result.output_data["experiment_id"]

    select_context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "operation": "select_winner",
            "experiment_id": experiment_id,
            "min_impressions": 100,
            "promote_on_selection": True,
        },
    )
    result = await agent.execute(select_context)

    assert result.success is True
    assert result.output_data["winner_variant_group"] is None
    assert result.output_data["promotion_applied"] is False
    assert result.output_data["promoted_listing_ids"] == []


@pytest.mark.asyncio
async def test_select_winner_with_promotion_updates_main_asset(db_session: AsyncSession):
    """ABTestManagerAgent should promote the selected winner when requested."""
    candidate = await _create_candidate(db_session, suffix="003")
    control = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="control", suffix="winner-a"
    )
    challenger = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="challenger", suffix="winner-b"
    )
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")

    control_assoc = ListingAssetAssociation(
        listing_id=listing.id,
        asset_id=control.id,
        display_order=0,
        is_main=True,
    )
    challenger_assoc = ListingAssetAssociation(
        listing_id=listing.id,
        asset_id=challenger.id,
        display_order=1,
        is_main=False,
    )
    db_session.add(control_assoc)
    db_session.add(challenger_assoc)
    await db_session.flush()

    await _record_asset_performance(
        db_session,
        asset_id=control.id,
        listing_id=listing.id,
        impressions=1000,
        clicks=80,
    )
    await _record_asset_performance(
        db_session,
        asset_id=challenger.id,
        listing_id=listing.id,
        impressions=1000,
        clicks=120,
    )

    agent = ABTestManagerAgent()
    create_context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "operation": "create_and_activate",
            "candidate_product_id": str(candidate.id),
        },
    )
    create_result = await agent.execute(create_context)
    experiment_id = create_result.output_data["experiment_id"]

    select_context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "operation": "select_winner",
            "experiment_id": experiment_id,
            "min_impressions": 100,
            "promote_on_selection": True,
        },
    )
    result = await agent.execute(select_context)

    assert result.success is True
    assert result.output_data["winner_variant_group"] == "challenger"
    assert result.output_data["promotion_applied"] is True
    assert str(listing.id) in result.output_data["promoted_listing_ids"]

    await db_session.refresh(control_assoc)
    await db_session.refresh(challenger_assoc)
    assert control_assoc.is_main is False
    assert challenger_assoc.is_main is True

    experiment = await db_session.get(Experiment, UUID(experiment_id))
    assert experiment is not None
    assert experiment.status.value == "completed"
    assert experiment.winner_variant_group == "challenger"


@pytest.mark.asyncio
async def test_set_winner_with_promotion_updates_main_asset(db_session: AsyncSession):
    """ABTestManagerAgent should manually set and promote a winner."""
    candidate = await _create_candidate(db_session, suffix="004")
    control = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="control", suffix="manual-a"
    )
    challenger = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="challenger", suffix="manual-b"
    )
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")

    control_assoc = ListingAssetAssociation(
        listing_id=listing.id,
        asset_id=control.id,
        display_order=0,
        is_main=True,
    )
    challenger_assoc = ListingAssetAssociation(
        listing_id=listing.id,
        asset_id=challenger.id,
        display_order=1,
        is_main=False,
    )
    db_session.add(control_assoc)
    db_session.add(challenger_assoc)
    await db_session.flush()

    agent = ABTestManagerAgent()
    create_context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "operation": "create_and_activate",
            "candidate_product_id": str(candidate.id),
        },
    )
    create_result = await agent.execute(create_context)
    experiment_id = create_result.output_data["experiment_id"]

    set_context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "operation": "set_winner",
            "experiment_id": experiment_id,
            "winner_variant_group": "challenger",
            "promote_on_selection": True,
        },
    )
    result = await agent.execute(set_context)

    assert result.success is True
    assert result.output_data["winner_variant_group"] == "challenger"
    assert result.output_data["promotion_applied"] is True
    assert str(listing.id) in result.output_data["promoted_listing_ids"]

    await db_session.refresh(control_assoc)
    await db_session.refresh(challenger_assoc)
    assert control_assoc.is_main is False
    assert challenger_assoc.is_main is True


@pytest.mark.asyncio
async def test_invalid_operation_returns_error(db_session: AsyncSession):
    """ABTestManagerAgent should reject unsupported operations."""
    agent = ABTestManagerAgent()
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={"operation": "unknown_operation"},
    )

    result = await agent.execute(context)

    assert result.success is False
    assert "Unsupported operation" in result.error_message
