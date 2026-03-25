"""Tests for listing metrics service."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CandidateStatus,
    PlatformListingStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import CandidateProduct, PlatformListing, StrategyRun
from app.services.listing_metrics_service import ListingMetricsService


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
async def test_record_daily_metrics_creates_new_record(db_session: AsyncSession):
    """ListingMetricsService should create a new daily record."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="test-001",
        title="Test Product",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

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

    service = ListingMetricsService()
    metric_date = date.today()

    record = await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=metric_date,
        impressions=1000,
        clicks=50,
        orders=5,
        units_sold=10,
        revenue=Decimal("299.90"),
    )

    assert record.listing_id == listing.id
    assert record.metric_date == metric_date
    assert record.impressions == 1000
    assert record.clicks == 50
    assert record.orders == 5
    assert record.units_sold == 10
    assert record.revenue == Decimal("299.90")


@pytest.mark.asyncio
async def test_record_daily_metrics_updates_existing_record(db_session: AsyncSession):
    """ListingMetricsService should update an existing record for the same day."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="test-002",
        title="Test Product 2",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("19.99"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.commit()

    service = ListingMetricsService()
    metric_date = date.today()

    first_record = await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=metric_date,
        impressions=500,
        clicks=25,
        orders=2,
        units_sold=4,
        revenue=Decimal("79.96"),
    )

    second_record = await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=metric_date,
        impressions=1500,
        clicks=75,
        orders=8,
        units_sold=16,
        revenue=Decimal("319.84"),
    )

    assert first_record.id == second_record.id
    assert second_record.impressions == 1500
    assert second_record.clicks == 75
    assert second_record.orders == 8
    assert second_record.units_sold == 16
    assert second_record.revenue == Decimal("319.84")


@pytest.mark.asyncio
async def test_get_metrics_history_returns_sorted_records(db_session: AsyncSession):
    """ListingMetricsService should return metrics history sorted by date."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="test-003",
        title="Test Product 3",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

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

    service = ListingMetricsService()
    today = date.today()

    await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=today - timedelta(days=2),
        impressions=100,
        clicks=10,
    )
    await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=today,
        impressions=300,
        clicks=30,
    )
    await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=today - timedelta(days=1),
        impressions=200,
        clicks=20,
    )

    history = await service.get_metrics_history(db_session, listing_id=listing.id)

    assert len(history) == 3
    assert history[0].metric_date == today - timedelta(days=2)
    assert history[1].metric_date == today - timedelta(days=1)
    assert history[2].metric_date == today


@pytest.mark.asyncio
async def test_get_metrics_summary_aggregates_correctly(db_session: AsyncSession):
    """ListingMetricsService should aggregate metrics correctly."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="test-004",
        title="Test Product 4",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("49.99"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.commit()

    service = ListingMetricsService()
    today = date.today()

    await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=today - timedelta(days=2),
        impressions=1000,
        clicks=50,
        orders=5,
        units_sold=10,
        revenue=Decimal("499.90"),
    )
    await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=today - timedelta(days=1),
        impressions=1500,
        clicks=75,
        orders=8,
        units_sold=16,
        revenue=Decimal("799.84"),
    )

    summary = await service.get_metrics_summary(db_session, listing_id=listing.id)

    assert summary["total_impressions"] == 2500
    assert summary["total_clicks"] == 125
    assert summary["total_orders"] == 13
    assert summary["total_units_sold"] == 26
    assert summary["total_revenue"] == Decimal("1299.74")
    assert summary["ctr"] == Decimal(125) / Decimal(2500)
    assert summary["order_rate"] == Decimal(13) / Decimal(125)


@pytest.mark.asyncio
async def test_record_daily_metrics_recovers_from_insert_conflict(db_session: AsyncSession):
    """ListingMetricsService should recover by re-reading when insert hits a unique conflict."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="test-006",
        title="Test Product 6",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

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

    service = ListingMetricsService()
    metric_date = date.today()

    existing = await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=metric_date,
        impressions=100,
        clicks=10,
        orders=1,
        units_sold=2,
        revenue=Decimal("139.98"),
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
        record = await service.record_daily_metrics(
            db_session,
            listing_id=listing.id,
            metric_date=metric_date,
            impressions=250,
            clicks=25,
            orders=3,
            units_sold=6,
            revenue=Decimal("419.94"),
        )

    history = await service.get_metrics_history(db_session, listing_id=listing.id)

    assert record.id == existing.id
    assert len(history) == 1
    assert history[0].impressions == 250
    assert history[0].clicks == 25
    assert history[0].orders == 3
    assert history[0].units_sold == 6
    assert history[0].revenue == Decimal("419.94")


@pytest.mark.asyncio
async def test_record_daily_metrics_refreshes_listing_rollups(db_session: AsyncSession):
    """ListingMetricsService should refresh PlatformListing.total_sales and total_revenue."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="test-005",
        title="Test Product 5",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("59.99"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
        total_sales=0,
        total_revenue=Decimal("0.00"),
    )
    db_session.add(listing)
    await db_session.commit()

    service = ListingMetricsService()
    today = date.today()

    await service.record_daily_metrics(
        db_session,
        listing_id=listing.id,
        metric_date=today,
        impressions=2000,
        clicks=100,
        orders=10,
        units_sold=20,
        revenue=Decimal("1199.80"),
    )

    await db_session.refresh(listing)

    assert listing.total_sales == 20
    assert listing.total_revenue == Decimal("1199.80")
