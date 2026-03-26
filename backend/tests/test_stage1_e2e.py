"""Stage 1 End-to-End Tests.

Validates the complete Stage 1 flow:
1. Product selection (candidate creation)
2. Multi-variant asset generation (C1)
3. Platform publishing
4. Performance data backfill
5. A/B test creation and activation
6. Winner selection and promotion
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ab_test_workflow import ABTestWorkflow
from app.agents.base.agent import AgentContext
from app.agents.content_asset_manager import ContentAssetManagerAgent
from app.agents.platform_publisher import PlatformPublisherAgent, PlatformSyncAgent
from app.core.enums import (
    CandidateStatus,
    ExperimentStatus,
    PlatformListingStatus,
    ProductLifecycle,
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
    ListingPerformanceDaily,
    PlatformListing,
    StrategyRun,
)
from app.services.asset_performance_service import AssetPerformanceService
from app.services.listing_metrics_service import ListingMetricsService


async def _create_strategy_run(db_session: AsyncSession) -> StrategyRun:
    """Create a strategy run for testing."""
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


@pytest.mark.asyncio
async def test_stage1_complete_flow_with_ab_test(db_session: AsyncSession):
    """Test complete Stage 1 flow: selection → assets → publish → metrics → A/B test → winner."""
    # =========================================================================
    # Step 1: Product Selection (Candidate Creation)
    # =========================================================================
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="stage1-e2e-001",
        title="Stage 1 E2E Test Product",
        category="electronics",
        currency="USD",
        platform_price=Decimal("10.00"),
        status=CandidateStatus.DISCOVERED,
        lifecycle_status=ProductLifecycle.DRAFT,
        internal_sku="DEY-E2E-001",
    )
    db_session.add(candidate)
    await db_session.commit()

    # =========================================================================
    # Step 2: Multi-Variant Asset Generation (C1 capability)
    # =========================================================================
    mock_comfyui = AsyncMock()
    mock_comfyui.generate_product_image = AsyncMock(return_value=b"fake_image_data")

    mock_minio = AsyncMock()
    mock_minio.upload_image = AsyncMock(
        side_effect=lambda **kwargs: f"https://minio.example.com/assets/{uuid4()}.png"
    )

    content_agent = ContentAssetManagerAgent(
        comfyui_client=mock_comfyui,
        minio_client=mock_minio,
    )

    # Generate control variant (2 styles)
    control_context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={
            "candidate_product_id": str(candidate.id),
            "asset_types": ["main_image"],
            "styles": ["minimalist"],
            "variant_count": 2,
            "variant_group": "control",
            "generate_count": 1,
            "platforms": ["temu"],
            "regions": ["us"],
        },
    )
    control_result = await content_agent.execute(control_context)
    assert control_result.success is True
    assert control_result.output_data["assets_created"] == 2
    assert control_result.output_data["variant_group"] == "control"

    # Generate challenger variant (2 styles)
    challenger_context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={
            "candidate_product_id": str(candidate.id),
            "asset_types": ["main_image"],
            "styles": ["luxury"],
            "variant_count": 2,
            "variant_group": "challenger",
            "generate_count": 1,
            "platforms": ["temu"],
            "regions": ["us"],
        },
    )
    challenger_result = await content_agent.execute(challenger_context)
    assert challenger_result.success is True
    assert challenger_result.output_data["assets_created"] == 2
    assert challenger_result.output_data["variant_group"] == "challenger"

    # Approve all assets
    await db_session.commit()
    assets_query = select(ContentAsset).where(ContentAsset.candidate_product_id == candidate.id)
    assets_result = await db_session.execute(assets_query)
    all_assets = list(assets_result.scalars().all())
    assert len(all_assets) == 4

    for asset in all_assets:
        asset.human_approved = True
    await db_session.commit()

    # Verify variant groups
    control_assets = [a for a in all_assets if a.variant_group == "control"]
    challenger_assets = [a for a in all_assets if a.variant_group == "challenger"]
    assert len(control_assets) == 2
    assert len(challenger_assets) == 2

    # =========================================================================
    # Step 3: Platform Publishing
    # =========================================================================
    publish_agent = PlatformPublisherAgent()
    publish_context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={
            "candidate_product_id": str(candidate.id),
            "target_platforms": [
                {"platform": "temu", "region": "us"},
            ],
            "pricing_strategy": "standard",
            "auto_approve": True,
        },
    )

    publish_result = await publish_agent.execute(publish_context)
    assert publish_result.success is True
    assert publish_result.output_data["published_count"] == 1

    # Verify listing created
    await db_session.commit()
    listings_query = select(PlatformListing).where(
        PlatformListing.candidate_product_id == candidate.id
    )
    listings_result = await db_session.execute(listings_query)
    listings = list(listings_result.scalars().all())
    assert len(listings) == 1

    listing = listings[0]
    assert listing.platform == TargetPlatform.TEMU
    assert listing.region == "us"
    assert listing.status == PlatformListingStatus.ACTIVE

    # Verify asset associations created
    assoc_query = select(ListingAssetAssociation).where(
        ListingAssetAssociation.listing_id == listing.id
    )
    assoc_result = await db_session.execute(assoc_query)
    associations = list(assoc_result.scalars().all())
    assert len(associations) == 4  # All 4 assets should be associated

    # =========================================================================
    # Step 4: Performance Data Backfill
    # =========================================================================
    metrics_service = ListingMetricsService()
    asset_perf_service = AssetPerformanceService()

    # Record listing-level metrics
    today = date.today()
    await metrics_service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=today,
        impressions=2000,
        clicks=200,
        orders=20,
        units_sold=20,
        revenue=Decimal("400.00"),
    )

    # Record asset-level performance (challenger performs better)
    for asset in control_assets:
        await asset_perf_service.record_daily_performance(
            db_session,
            asset_id=asset.id,
            listing_id=listing.id,
            metric_date=today,
            impressions=900,
            clicks=72,  # 8% CTR
            orders=7,
            units_sold=7,
            revenue=Decimal("140.00"),
            usage_count=1,
        )

    for asset in challenger_assets:
        await asset_perf_service.record_daily_performance(
            db_session,
            asset_id=asset.id,
            listing_id=listing.id,
            metric_date=today,
            impressions=1100,
            clicks=132,  # 12% CTR (better)
            orders=13,
            units_sold=13,
            revenue=Decimal("260.00"),
            usage_count=1,
        )

    await db_session.commit()

    # Verify metrics persisted
    perf_query = select(ListingPerformanceDaily).where(
        ListingPerformanceDaily.listing_id == listing.id
    )
    perf_result = await db_session.execute(perf_query)
    perf_records = list(perf_result.scalars().all())
    assert len(perf_records) == 1
    assert perf_records[0].impressions == 2000
    assert perf_records[0].clicks == 200

    # =========================================================================
    # Step 5: A/B Test Creation and Activation
    # =========================================================================
    workflow = ABTestWorkflow()
    create_result = await workflow.execute_operation(
        db_session,
        operation="create_and_activate",
        candidate_product_id=candidate.id,
        name="Stage 1 E2E A/B Test",
        metric_goal="ctr",
    )

    assert create_result["success"] is True
    assert create_result["output_data"]["status"] == "active"
    assert create_result["output_data"]["variant_count"] == 2

    experiment_id = UUID(create_result["output_data"]["experiment_id"])
    experiment = await db_session.get(Experiment, experiment_id)
    assert experiment is not None
    assert experiment.status == ExperimentStatus.ACTIVE
    assert experiment.metric_goal == "ctr"

    # =========================================================================
    # Step 6: Winner Selection and Promotion
    # =========================================================================
    select_result = await workflow.execute_operation(
        db_session,
        operation="select_winner",
        experiment_id=experiment_id,
        min_impressions=100,
        promote_on_selection=True,
    )

    assert select_result["success"] is True
    assert select_result["output_data"]["winner_variant_group"] == "challenger"
    assert select_result["output_data"]["promotion_applied"] is True
    assert len(select_result["output_data"]["promoted_listing_ids"]) == 1

    # Verify experiment completed
    await db_session.refresh(experiment)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert experiment.winner_variant_group == "challenger"
    assert experiment.winner_selected_at is not None

    # Verify main asset updated to challenger
    await db_session.refresh(listing)
    main_assoc_query = (
        select(ListingAssetAssociation)
        .where(
            ListingAssetAssociation.listing_id == listing.id,
            ListingAssetAssociation.is_main == True,
        )
    )
    main_assoc_result = await db_session.execute(main_assoc_query)
    main_assoc = main_assoc_result.scalar_one()

    main_asset = await db_session.get(ContentAsset, main_assoc.asset_id)
    assert main_asset.variant_group == "challenger"

    # =========================================================================
    # Final Verification: Complete Data Flow
    # =========================================================================
    # 1. Candidate lifecycle progressed
    await db_session.refresh(candidate)
    assert candidate.lifecycle_status == ProductLifecycle.PUBLISHED

    # 2. All assets created and approved
    assert len(all_assets) == 4
    assert all(asset.human_approved for asset in all_assets)

    # 3. Listing active with correct pricing
    assert listing.status == PlatformListingStatus.ACTIVE
    assert listing.price > candidate.platform_price

    # 4. Performance data captured
    assert len(perf_records) == 1

    # 5. A/B test completed with winner
    assert experiment.status == ExperimentStatus.COMPLETED
    assert experiment.winner_variant_group == "challenger"

    # 6. Winner promoted to main asset
    assert main_asset.variant_group == "challenger"


@pytest.mark.asyncio
async def test_stage1_metrics_sync_integration(db_session: AsyncSession):
    """Test platform sync agent integration with metrics backfill."""
    # Create test data
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="sync-test-001",
        title="Sync Test Product",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        platform_listing_id="TEMU-SYNC-001",
        price=Decimal("29.99"),
        currency="USD",
        inventory=100,
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.commit()

    # Mock sync service
    sync_agent = PlatformSyncAgent()
    sync_agent.sync_service.sync_listing_metrics = AsyncMock(
        return_value={"status": "ok", "synced_days": 1}
    )

    # Execute sync
    today = date.today()
    sync_context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={
            "sync_type": "listing_metrics",
            "start_date": str(today),
            "end_date": str(today),
        },
    )

    sync_result = await sync_agent.execute(sync_context)

    assert sync_result.success is True
    assert sync_result.output_data["synced_count"] == 1
    assert sync_result.output_data["failed_count"] == 0

    # Verify sync metadata updated
    await db_session.refresh(listing)
    assert listing.last_synced_at is not None
    assert listing.sync_error is None
