"""Tests for A/B test workflow orchestration."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ab_test_workflow import ABTestWorkflow
from app.core.enums import (
    AgentRunStatus,
    AssetType,
    CandidateStatus,
    PlatformListingStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import (
    AgentRun,
    CandidateProduct,
    ContentAsset,
    Experiment,
    ListingAssetAssociation,
    PlatformListing,
    RunEvent,
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
        source_product_id=f"abtest-workflow-{suffix}",
        title=f"AB Test Workflow Product {suffix}",
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


async def _create_experiment_with_variants(
    db_session: AsyncSession,
    *,
    suffix: str,
) -> tuple[CandidateProduct, ContentAsset, ContentAsset, Experiment]:
    candidate = await _create_candidate(db_session, suffix=suffix)
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="control", suffix=f"{suffix}-a")
    await _create_asset(
        db_session,
        candidate_id=candidate.id,
        variant_group="challenger",
        suffix=f"{suffix}-b",
    )

    service = ExperimentService()
    experiment = await service.create_experiment(
        db_session,
        candidate_product_id=candidate.id,
        name=f"Experiment {suffix}",
    )
    experiment = await service.activate_experiment(db_session, experiment_id=experiment.id)
    await db_session.commit()

    control = next(asset for asset in candidate.content_assets if asset.variant_group == "control")
    challenger = next(asset for asset in candidate.content_assets if asset.variant_group == "challenger")
    return candidate, control, challenger, experiment


async def _get_latest_agent_run(db_session: AsyncSession, *, strategy_run_id) -> AgentRun:
    stmt = select(AgentRun).where(AgentRun.strategy_run_id == strategy_run_id)
    agent_runs = list((await db_session.execute(stmt)).scalars().all())
    assert len(agent_runs) == 1
    return agent_runs[0]


async def _get_agent_events(db_session: AsyncSession, *, agent_run_id) -> list[RunEvent]:
    stmt = select(RunEvent).where(RunEvent.agent_run_id == agent_run_id)
    return list((await db_session.execute(stmt)).scalars().all())


@pytest.mark.asyncio
async def test_create_and_activate_records_agent_run(db_session: AsyncSession):
    """ABTestWorkflow should record observability data for create_and_activate."""
    candidate = await _create_candidate(db_session, suffix="001")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="control", suffix="create-a")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="challenger", suffix="create-b")
    workflow = ABTestWorkflow()

    result = await workflow.execute_operation(
        db_session,
        operation="create_and_activate",
        candidate_product_id=candidate.id,
        name="CTR experiment",
    )

    assert result["success"] is True

    agent_run = await _get_latest_agent_run(db_session, strategy_run_id=candidate.strategy_run_id)
    assert agent_run.agent_name == "ab_test_manager"
    assert agent_run.step_name == "ab_test_create_and_activate"
    assert agent_run.status == AgentRunStatus.COMPLETED
    assert agent_run.input_data == {
        "operation": "create_and_activate",
        "candidate_product_id": str(candidate.id),
        "name": "CTR experiment",
    }
    assert agent_run.output_data["operation"] == "create_and_activate"

    events = await _get_agent_events(db_session, agent_run_id=agent_run.id)
    assert len(events) == 2
    assert {event.event_type for event in events} == {
        "agent.ab_test_create_and_activate.started",
        "agent.ab_test_create_and_activate.completed",
    }


@pytest.mark.asyncio
async def test_select_winner_defaults_to_no_promotion(db_session: AsyncSession):
    """ABTestWorkflow should select a winner without changing main asset by default."""
    candidate = await _create_candidate(db_session, suffix="002")
    control = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="control", suffix="default-a"
    )
    challenger = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="challenger", suffix="default-b"
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

    create_workflow = ABTestWorkflow()
    create_result = await create_workflow.execute_operation(
        db_session,
        operation="create_and_activate",
        candidate_product_id=candidate.id,
    )
    experiment_id = UUID(create_result["output_data"]["experiment_id"])

    workflow = ABTestWorkflow()
    result = await workflow.execute_operation(
        db_session,
        operation="select_winner",
        experiment_id=experiment_id,
        min_impressions=100,
    )

    assert result["success"] is True
    assert result["output_data"]["winner_variant_group"] == "challenger"
    assert result["output_data"]["promotion_applied"] is False
    assert result["output_data"]["promoted_listing_ids"] == []

    await db_session.refresh(control_assoc)
    await db_session.refresh(challenger_assoc)
    assert control_assoc.is_main is True
    assert challenger_assoc.is_main is False

    stmt = select(AgentRun).where(
        AgentRun.strategy_run_id == candidate.strategy_run_id,
        AgentRun.step_name == "ab_test_select_winner",
    )
    agent_run = (await db_session.execute(stmt)).scalar_one()
    assert agent_run.status == AgentRunStatus.COMPLETED

    events = await _get_agent_events(db_session, agent_run_id=agent_run.id)
    assert len(events) == 2


@pytest.mark.asyncio
async def test_promote_winner_updates_main_asset(db_session: AsyncSession):
    """ABTestWorkflow should explicitly promote a selected winner."""
    candidate = await _create_candidate(db_session, suffix="003")
    control = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="control", suffix="promote-a"
    )
    challenger = await _create_asset(
        db_session, candidate_id=candidate.id, variant_group="challenger", suffix="promote-b"
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

    workflow = ABTestWorkflow()
    create_result = await workflow.execute_operation(
        db_session,
        operation="create_and_activate",
        candidate_product_id=candidate.id,
    )
    experiment_id = UUID(create_result["output_data"]["experiment_id"])

    select_result = await workflow.execute_operation(
        db_session,
        operation="set_winner",
        experiment_id=experiment_id,
        winner_variant_group="challenger",
    )
    assert select_result["success"] is True

    promote_result = await workflow.execute_operation(
        db_session,
        operation="promote_winner",
        experiment_id=experiment_id,
    )

    assert promote_result["success"] is True
    assert promote_result["output_data"]["winner_variant_group"] == "challenger"
    assert str(listing.id) in promote_result["output_data"]["promoted_listing_ids"]

    await db_session.refresh(control_assoc)
    await db_session.refresh(challenger_assoc)
    assert control_assoc.is_main is False
    assert challenger_assoc.is_main is True

    stmt = select(AgentRun).where(
        AgentRun.strategy_run_id == candidate.strategy_run_id,
        AgentRun.step_name == "ab_test_promote_winner",
    )
    agent_run = (await db_session.execute(stmt)).scalar_one()
    assert agent_run.status == AgentRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_strategy_run_resolution_supports_candidate_and_experiment_ids(db_session: AsyncSession):
    """ABTestWorkflow should resolve strategy_run from both candidate and experiment relationships."""
    candidate = await _create_candidate(db_session, suffix="004")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="control", suffix="resolve-a")
    await _create_asset(db_session, candidate_id=candidate.id, variant_group="challenger", suffix="resolve-b")
    workflow = ABTestWorkflow()

    create_result = await workflow.execute_operation(
        db_session,
        operation="create_and_activate",
        candidate_product_id=candidate.id,
    )
    experiment_id = UUID(create_result["output_data"]["experiment_id"])

    summary_result = await workflow.execute_operation(
        db_session,
        operation="get_summary",
        experiment_id=experiment_id,
    )
    assert summary_result["success"] is True

    stmt = select(AgentRun).where(AgentRun.strategy_run_id == candidate.strategy_run_id)
    agent_runs = list((await db_session.execute(stmt)).scalars().all())
    step_names = {agent_run.step_name for agent_run in agent_runs}
    assert "ab_test_create_and_activate" in step_names
    assert "ab_test_get_summary" in step_names


@pytest.mark.asyncio
async def test_missing_ids_raise_resolution_errors(db_session: AsyncSession):
    """ABTestWorkflow should reject missing or unknown identifiers during strategy_run resolution."""
    workflow = ABTestWorkflow()

    with pytest.raises(ValueError, match="candidate_product_id required for create_and_activate"):
        await workflow.execute_operation(db_session, operation="create_and_activate")

    with pytest.raises(ValueError, match="Candidate not found"):
        await workflow.execute_operation(
            db_session,
            operation="create_and_activate",
            candidate_product_id=uuid4(),
        )

    with pytest.raises(ValueError, match="experiment_id required for get_summary"):
        await workflow.execute_operation(db_session, operation="get_summary")

    with pytest.raises(ValueError, match="Experiment not found"):
        await workflow.execute_operation(
            db_session,
            operation="get_summary",
            experiment_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_invalid_operation_marks_agent_run_failed(db_session: AsyncSession):
    """ABTestWorkflow should record failed AgentRun for unsupported operations."""
    candidate = await _create_candidate(db_session, suffix="005")
    workflow = ABTestWorkflow()

    result = await workflow.execute_operation(
        db_session,
        operation="unknown_operation",
        candidate_product_id=candidate.id,
    )

    assert result["success"] is False
    assert "Unsupported operation" in result["error_message"]

    agent_run = await _get_latest_agent_run(db_session, strategy_run_id=candidate.strategy_run_id)
    assert agent_run.step_name == "ab_test_unknown_operation"
    assert agent_run.status == AgentRunStatus.FAILED
    assert "Unsupported operation" in agent_run.error_message

    events = await _get_agent_events(db_session, agent_run_id=agent_run.id)
    assert len(events) == 2
    completed_event = next(event for event in events if event.event_type.endswith(".completed"))
    assert completed_event.event_payload["success"] is False
