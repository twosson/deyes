"""Tests for asset performance service."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AssetType,
    CandidateStatus,
    PlatformListingStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import CandidateProduct, ContentAsset, PlatformListing, StrategyRun
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


@pytest.mark.asyncio
async def test_record_daily_performance_creates_new_record(db_session: AsyncSession):
    """AssetPerformanceService should create a new daily record."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="asset-test-001",
        title="Asset Test Product",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset1.png",
    )
    db_session.add(asset)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("29.99"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.commit()

    service = AssetPerformanceService()
    metric_date = date.today()

    record = await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
        metric_date=metric_date,
        impressions=500,
        clicks=25,
        orders=2,
        units_sold=4,
        revenue=Decimal("119.96"),
        usage_count=3,
    )

    assert record.asset_id == asset.id
    assert record.listing_id == listing.id
    assert record.metric_date == metric_date
    assert record.impressions == 500
    assert record.clicks == 25
    assert record.orders == 2
    assert record.units_sold == 4
    assert record.revenue == Decimal("119.96")
    assert record.usage_count == 3


@pytest.mark.asyncio
async def test_record_daily_performance_updates_existing_record(db_session: AsyncSession):
    """AssetPerformanceService should update an existing record for the same asset/listing/day."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="asset-test-002",
        title="Asset Test Product 2",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset2.png",
    )
    db_session.add(asset)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("39.99"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.commit()

    service = AssetPerformanceService()
    metric_date = date.today()

    first_record = await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
        metric_date=metric_date,
        impressions=300,
        clicks=15,
        usage_count=2,
    )

    second_record = await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
        metric_date=metric_date,
        impressions=800,
        clicks=40,
        orders=4,
        units_sold=8,
        revenue=Decimal("319.92"),
        usage_count=5,
    )

    history = await service.get_asset_history(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
    )

    assert first_record.id == second_record.id
    assert len(history) == 1
    assert second_record.impressions == 800
    assert second_record.clicks == 40
    assert second_record.orders == 4
    assert second_record.units_sold == 8
    assert second_record.revenue == Decimal("319.92")
    assert second_record.usage_count == 5


@pytest.mark.asyncio
async def test_same_asset_can_have_separate_records_per_listing(db_session: AsyncSession):
    """AssetPerformanceService should keep performance records separate across listings."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="asset-test-003",
        title="Asset Test Product 3",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset3.png",
    )
    db_session.add(asset)

    listing1 = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("49.99"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    listing2 = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="uk",
        price=Decimal("44.99"),
        currency="GBP",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing1)
    db_session.add(listing2)
    await db_session.commit()

    service = AssetPerformanceService()
    metric_date = date.today()

    await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing1.id,
        metric_date=metric_date,
        impressions=600,
        clicks=30,
        usage_count=4,
    )
    await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing2.id,
        metric_date=metric_date,
        impressions=900,
        clicks=45,
        usage_count=6,
    )

    full_history = await service.get_asset_history(db_session, asset_id=asset.id)
    listing1_history = await service.get_asset_history(db_session, asset_id=asset.id, listing_id=listing1.id)
    listing2_history = await service.get_asset_history(db_session, asset_id=asset.id, listing_id=listing2.id)

    assert len(full_history) == 2
    assert len(listing1_history) == 1
    assert len(listing2_history) == 1
    assert listing1_history[0].listing_id == listing1.id
    assert listing2_history[0].listing_id == listing2.id


@pytest.mark.asyncio
async def test_get_asset_summary_aggregates_correctly(db_session: AsyncSession):
    """AssetPerformanceService should aggregate asset performance correctly."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="asset-test-004",
        title="Asset Test Product 4",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset4.png",
    )
    db_session.add(asset)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("59.99"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.commit()

    service = AssetPerformanceService()
    today = date.today()

    await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
        metric_date=today - timedelta(days=1),
        impressions=400,
        clicks=20,
        orders=2,
        units_sold=4,
        revenue=Decimal("239.96"),
        usage_count=3,
    )
    await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
        metric_date=today,
        impressions=600,
        clicks=30,
        orders=3,
        units_sold=6,
        revenue=Decimal("359.94"),
        usage_count=5,
    )

    summary = await service.get_asset_summary(db_session, asset_id=asset.id)

    assert summary["total_impressions"] == 1000
    assert summary["total_clicks"] == 50
    assert summary["total_orders"] == 5
    assert summary["total_units_sold"] == 10
    assert summary["total_revenue"] == Decimal("599.90")
    assert summary["total_usage_count"] == 8
    assert summary["ctr"] == Decimal(50) / Decimal(1000)


@pytest.mark.asyncio
async def test_record_daily_performance_recovers_from_insert_conflict(db_session: AsyncSession):
    """AssetPerformanceService should recover by re-reading when insert hits a unique conflict."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="asset-test-006",
        title="Asset Test Product 6",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset6.png",
    )
    db_session.add(asset)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("79.99"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.commit()

    service = AssetPerformanceService()
    metric_date = date.today()

    existing = await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
        metric_date=metric_date,
        impressions=120,
        clicks=12,
        orders=1,
        units_sold=2,
        revenue=Decimal("159.98"),
        usage_count=1,
    )
    await db_session.commit()

    original_execute = db_session.execute
    state = {"execute_calls": 0}

    async def mock_execute(*args, **kwargs):
        state["execute_calls"] += 1
        result = await original_execute(*args, **kwargs)
        if state["execute_calls"] == 1:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result
        return result

    with patch.object(db_session, "execute", new=AsyncMock(side_effect=mock_execute)):
        record = await service.record_daily_performance(
            db_session,
            asset_id=asset.id,
            listing_id=listing.id,
            metric_date=metric_date,
            impressions=320,
            clicks=32,
            orders=4,
            units_sold=8,
            revenue=Decimal("639.92"),
            usage_count=5,
        )

    history = await service.get_asset_history(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
    )

    assert record.id == existing.id
    assert len(history) == 1
    assert history[0].impressions == 320
    assert history[0].clicks == 32
    assert history[0].orders == 4
    assert history[0].units_sold == 8
    assert history[0].revenue == Decimal("639.92")
    assert history[0].usage_count == 5


@pytest.mark.asyncio
async def test_record_daily_performance_refreshes_asset_usage_count(db_session: AsyncSession):
    """AssetPerformanceService should refresh ContentAsset.usage_count."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="asset-test-005",
        title="Asset Test Product 5",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/asset5.png",
        usage_count=0,
    )
    db_session.add(asset)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("69.99"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.commit()

    service = AssetPerformanceService()
    today = date.today()

    await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
        metric_date=today - timedelta(days=1),
        usage_count=2,
    )
    await service.record_daily_performance(
        db_session,
        asset_id=asset.id,
        listing_id=listing.id,
        metric_date=today,
        usage_count=4,
    )

    await db_session.refresh(asset)

    assert asset.usage_count == 6
