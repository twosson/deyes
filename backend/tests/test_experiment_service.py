"""Tests for experiment service."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AssetType,
    CandidateStatus,
    ExperimentStatus,
    PlatformListingStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    ContentAsset,
    ListingAssetAssociation,
    PlatformListing,
    StrategyRun,
)
from app.services.asset_performance_service import AssetPerformanceService
from app.services.experiment_service import ExperimentService


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
        source_product_id=f"experiment-{suffix}",
        title=f"Experiment Product {suffix}",
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
async def test_create_experiment_creates_draft_with_defaults(db_session: AsyncSession):
    """ExperimentService should create a draft experiment with default metric."""
    candidate = await _create_candidate(db_session, suffix="001")
    service = ExperimentService()

    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="Main image CTR test",
    )

    assert experiment.candidate_product_id == candidate.id
    assert experiment.name == "Main image CTR test"
    assert experiment.status == ExperimentStatus.DRAFT
    assert experiment.metric_goal == "ctr"
    assert experiment.winner_variant_group is None


@pytest.mark.asyncio
async def test_create_experiment_rejects_unsupported_metric_goal(db_session: AsyncSession):
    """ExperimentService should reject unsupported metric goals."""
    candidate = await _create_candidate(db_session, suffix="002")
    service = ExperimentService()

    with pytest.raises(ValueError, match="Unsupported metric_goal"):
        await service.create_experiment(
            db_session,
            candidate_product_id=candidate.id,
            name="Invalid metric test",
            metric_goal="bounce_rate",
        )


@pytest.mark.asyncio
async def test_activate_experiment_requires_two_variant_groups(db_session: AsyncSession):
    """ExperimentService should require at least two variant groups before activation."""
    candidate = await _create_candidate(db_session, suffix="003")
    await _create_asset(
        db_session,
        candidate_id=candidate.id,
        variant_group="control",
        suffix="control-only",
    )
    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="Single variant test",
    )

    with pytest.raises(ValueError, match="at least two variant groups"):
        await service.activate_experiment(db_session, experiment_id=experiment.id)


@pytest.mark.asyncio
async def test_get_experiment_variants_groups_assets(db_session: AsyncSession):
    """ExperimentService should return grouped variant counts for a candidate product."""
    candidate = await _create_candidate(db_session, suffix="004")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="control", suffix="a1")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="control", suffix="a2")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="challenger", suffix="b1")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group=None, suffix="ignored")

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="Variant grouping test",
    )

    variants = await service.get_experiment_variants(db_session, experiment_id=experiment.id)

    assert variants == [
        {"variant_group": "challenger", "asset_count": 1},
        {"variant_group": "control", "asset_count": 2},
    ]


@pytest.mark.asyncio
async def test_get_experiment_summary_aggregates_and_filters_metrics(db_session: AsyncSession):
    """ExperimentService should aggregate metrics by variant group and respect filters."""
    candidate = await _create_candidate(db_session, suffix="005")
    control = await _create_asset(
        db_session,
        candidate_id=candidate.id,
        variant_group="control",
        suffix="summary-control",
    )
    challenger = await _create_asset(
        db_session,
        candidate_id=candidate.id,
        variant_group="challenger",
        suffix="summary-challenger",
    )
    us_listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")
    uk_listing = await _create_listing(db_session, candidate_id=candidate.id, region="uk")

    await _record_asset_performance(
        db_session,
        asset_id=control.id,
        listing_id=us_listing.id,
        impressions=1000,
        clicks=100,
        orders=10,
        units_sold=12,
        revenue=Decimal("240.00"),
        usage_count=1,
    )
    await _record_asset_performance(
        db_session,
        asset_id=challenger.id,
        listing_id=us_listing.id,
        impressions=800,
        clicks=80,
        orders=8,
        units_sold=9,
        revenue=Decimal("180.00"),
        usage_count=1,
    )
    await _record_asset_performance(
        db_session,
        asset_id=control.id,
        listing_id=uk_listing.id,
        impressions=500,
        clicks=5,
        orders=1,
        units_sold=1,
        revenue=Decimal("25.00"),
        usage_count=1,
    )

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="US only summary test",
        target_platform=TargetPlatform.TEMU,
        region="us",
    )

    summary = await service.get_experiment_summary(db_session, experiment_id=experiment.id)
    variants = {item["variant_group"]: item for item in summary["variants"]}

    assert summary["status"] == ExperimentStatus.DRAFT.value
    assert summary["winner_variant_group"] is None
    assert set(variants) == {"control", "challenger"}

    assert variants["control"]["impressions"] == 1000
    assert variants["control"]["clicks"] == 100
    assert variants["control"]["orders"] == 10
    assert variants["control"]["units_sold"] == 12
    assert variants["control"]["revenue"] == Decimal("240.00")
    assert variants["control"]["ctr"] == Decimal("0.1")
    assert variants["control"]["cvr"] == Decimal("0.1")

    assert variants["challenger"]["impressions"] == 800
    assert variants["challenger"]["clicks"] == 80
    assert variants["challenger"]["orders"] == 8
    assert variants["challenger"]["units_sold"] == 9
    assert variants["challenger"]["revenue"] == Decimal("180.00")
    assert variants["challenger"]["ctr"] == Decimal("0.1")
    assert variants["challenger"]["cvr"] == Decimal("0.1")


@pytest.mark.asyncio
async def test_select_winner_chooses_best_ctr_variant(db_session: AsyncSession):
    """ExperimentService should choose the highest-CTR variant when selecting a winner."""
    candidate = await _create_candidate(db_session, suffix="006")
    control = await _create_asset(
        db_session,
        candidate_id=candidate.id,
        variant_group="control",
        suffix="winner-control",
    )
    challenger = await _create_asset(
        db_session,
        candidate_id=candidate.id,
        variant_group="challenger",
        suffix="winner-challenger",
    )
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")

    await _record_asset_performance(
        db_session,
        asset_id=control.id,
        listing_id=listing.id,
        impressions=1000,
        clicks=80,
        orders=8,
        revenue=Decimal("160.00"),
    )
    await _record_asset_performance(
        db_session,
        asset_id=challenger.id,
        listing_id=listing.id,
        impressions=1000,
        clicks=120,
        orders=10,
        revenue=Decimal("220.00"),
    )

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="Winner selection test",
        metric_goal="ctr",
    )
    await service.activate_experiment(db_session, experiment_id=experiment.id)

    winner = await service.select_winner(
        db_session,
        experiment_id=experiment.id,
        min_impressions=100,
    )
    await db_session.refresh(experiment)

    assert winner == "challenger"
    assert experiment.status == ExperimentStatus.COMPLETED
    assert experiment.winner_variant_group == "challenger"
    assert experiment.winner_selected_at is not None


@pytest.mark.asyncio
async def test_select_winner_returns_none_when_threshold_not_met(db_session: AsyncSession):
    """ExperimentService should not select a winner when variants lack enough impressions."""
    candidate = await _create_candidate(db_session, suffix="007")
    control = await _create_asset(
        db_session,
        candidate_id=candidate.id,
        variant_group="control",
        suffix="threshold-control",
    )
    challenger = await _create_asset(
        db_session,
        candidate_id=candidate.id,
        variant_group="challenger",
        suffix="threshold-challenger",
    )
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")

    await _record_asset_performance(
        db_session,
        asset_id=control.id,
        listing_id=listing.id,
        impressions=80,
        clicks=12,
    )
    await _record_asset_performance(
        db_session,
        asset_id=challenger.id,
        listing_id=listing.id,
        impressions=90,
        clicks=18,
    )

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="Threshold test",
    )
    await service.activate_experiment(db_session, experiment_id=experiment.id)

    winner = await service.select_winner(
        db_session,
        experiment_id=experiment.id,
        min_impressions=100,
    )
    await db_session.refresh(experiment)

    assert winner is None
    assert experiment.status == ExperimentStatus.ACTIVE
    assert experiment.winner_variant_group is None


@pytest.mark.asyncio
async def test_set_winner_rejects_unknown_variant_group(db_session: AsyncSession):
    """ExperimentService should reject manual winner groups that are not in the experiment."""
    candidate = await _create_candidate(db_session, suffix="008")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="control", suffix="set-a")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="challenger", suffix="set-b")

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="Manual winner validation test",
    )

    with pytest.raises(ValueError, match="Variant group not found"):
        await service.set_winner(
            db_session,
            experiment_id=experiment.id,
            winner_variant_group="ghost",
        )


@pytest.mark.asyncio
async def test_set_winner_marks_experiment_completed(db_session: AsyncSession):
    """ExperimentService should allow manually setting a known winner variant."""
    candidate = await _create_candidate(db_session, suffix="009")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="control", suffix="manual-a")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="challenger", suffix="manual-b")

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="Manual winner test",
    )

    updated = await service.set_winner(
        db_session,
        experiment_id=experiment.id,
        winner_variant_group="control",
    )

    assert updated.status == ExperimentStatus.COMPLETED
    assert updated.winner_variant_group == "control"
    assert updated.winner_selected_at is not None


@pytest.mark.asyncio
async def test_promote_winner_updates_main_flag(db_session: AsyncSession):
    """ExperimentService should update is_main for winner assets."""
    candidate = await _create_candidate(db_session, suffix="010")
    control_asset = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="control", suffix="promote-control"
    )
    challenger_asset = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="challenger", suffix="promote-challenger"
    )
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")

    # Create associations: control is main initially
    control_assoc = ListingAssetAssociation(
        listing_id=listing.id,
        asset_id=control_asset.id,
        display_order=0,
        is_main=True,
    )
    challenger_assoc = ListingAssetAssociation(
        listing_id=listing.id,
        asset_id=challenger_asset.id,
        display_order=1,
        is_main=False,
    )
    db_session.add(control_assoc)
    db_session.add(challenger_assoc)
    await db_session.flush()

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="Promotion test",
    )
    await service.set_winner(
        db_session,
        experiment_id=experiment.id,
        winner_variant_group="challenger",
    )

    result = await service.promote_winner(db_session, experiment_id=experiment.id)

    assert result["winner_variant_group"] == "challenger"
    assert str(listing.id) in result["promoted_listing_ids"]
    assert result["updated_association_count"] == 2

    # Verify associations
    await db_session.refresh(control_assoc)
    await db_session.refresh(challenger_assoc)
    assert control_assoc.is_main is False
    assert challenger_assoc.is_main is True


@pytest.mark.asyncio
async def test_promote_winner_skips_listings_without_winner_assets(db_session: AsyncSession):
    """ExperimentService should skip listings that lack winner variant assets."""
    candidate = await _create_candidate(db_session, suffix="011")
    control_asset = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="control", suffix="skip-control"
    )
    challenger_asset = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="challenger", suffix="skip-challenger"
    )
    listing_with_winner = await _create_listing(db_session, candidate_id=candidate.id, region="us")
    listing_without_winner = await _create_listing(db_session, candidate_id=candidate.id, region="uk")

    # listing_with_winner has both assets
    db_session.add(
        ListingAssetAssociation(
            listing_id=listing_with_winner.id,
            asset_id=control_asset.id,
            display_order=0,
            is_main=True,
        )
    )
    db_session.add(
        ListingAssetAssociation(
            listing_id=listing_with_winner.id,
            asset_id=challenger_asset.id,
            display_order=1,
            is_main=False,
        )
    )

    # listing_without_winner only has control
    db_session.add(
        ListingAssetAssociation(
            listing_id=listing_without_winner.id,
            asset_id=control_asset.id,
            display_order=0,
            is_main=True,
        )
    )
    await db_session.flush()

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="Skip test",
    )
    await service.set_winner(
        db_session,
        experiment_id=experiment.id,
        winner_variant_group="challenger",
    )

    result = await service.promote_winner(db_session, experiment_id=experiment.id)

    assert str(listing_with_winner.id) in result["promoted_listing_ids"]
    assert str(listing_without_winner.id) in result["skipped_listing_ids"]


@pytest.mark.asyncio
async def test_promote_winner_rejects_experiment_without_winner(db_session: AsyncSession):
    """ExperimentService should reject promotion when no winner is selected."""
    candidate = await _create_candidate(db_session, suffix="012")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="control", suffix="no-winner-a")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="challenger", suffix="no-winner-b")

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name="No winner test",
    )

    with pytest.raises(ValueError, match="has no winner selected"):
        await service.promote_winner(db_session, experiment_id=experiment.id)

