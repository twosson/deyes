"""Tests for PerformanceCalculator service."""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.core.enums import (
    CandidateStatus,
    PlatformListingStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import CandidateProduct, ListingPerformanceDaily, PlatformListing, StrategyRun
from app.services.performance_calculator import PerformanceCalculator


@pytest.mark.asyncio
async def test_calculate_ctr():
    """Test CTR calculation."""
    assert PerformanceCalculator.calculate_ctr(1000, 50) == 0.05
    assert PerformanceCalculator.calculate_ctr(0, 0) == 0.0
    assert PerformanceCalculator.calculate_ctr(100, 0) == 0.0


@pytest.mark.asyncio
async def test_calculate_cvr():
    """Test CVR calculation."""
    assert PerformanceCalculator.calculate_cvr(100, 10) == 0.1
    assert PerformanceCalculator.calculate_cvr(0, 0) == 0.0
    assert PerformanceCalculator.calculate_cvr(50, 0) == 0.0


@pytest.mark.asyncio
async def test_calculate_roi():
    """Test ROI calculation."""
    assert PerformanceCalculator.calculate_roi(Decimal("300"), Decimal("100")) == Decimal("2.0")
    assert PerformanceCalculator.calculate_roi(Decimal("100"), Decimal("100")) == Decimal("0")
    assert PerformanceCalculator.calculate_roi(Decimal("100"), Decimal("0")) == Decimal("0")


@pytest.mark.asyncio
async def test_calculate_roas():
    """Test ROAS calculation."""
    assert PerformanceCalculator.calculate_roas(Decimal("500"), Decimal("100")) == Decimal("5.0")
    assert PerformanceCalculator.calculate_roas(Decimal("100"), Decimal("0")) == Decimal("0")


@pytest.mark.asyncio
async def test_get_listing_7day_metrics_no_data(db_session):
    """Test get_listing_7day_metrics with no data."""
    listing_id = uuid4()
    metrics = await PerformanceCalculator.get_listing_7day_metrics(db_session, listing_id)
    assert metrics is None


@pytest.mark.asyncio
async def test_get_listing_7day_metrics_with_data(db_session):
    """Test get_listing_7day_metrics with performance data."""
    # Create strategy run
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.MANUAL,
        status=StrategyRunStatus.COMPLETED,
    )
    db_session.add(strategy_run)

    # Create candidate
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.TEMU,
        title="Test Product",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    # Create listing
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.flush()

    # Create 7 days of performance data
    for i in range(7):
        perf = ListingPerformanceDaily(
            id=uuid4(),
            listing_id=listing.id,
            metric_date=date.today() - timedelta(days=i),
            impressions=1000,
            clicks=50,
            orders=5,
            units_sold=5,
            revenue=Decimal("250"),
            ad_spend=Decimal("50"),
        )
        db_session.add(perf)
    await db_session.flush()

    # Get metrics
    metrics = await PerformanceCalculator.get_listing_7day_metrics(db_session, listing.id)

    assert metrics is not None
    assert metrics["data_points"] == 7
    assert metrics["total_impressions"] == 7000
    assert metrics["total_clicks"] == 350
    assert metrics["total_orders"] == 35
    assert metrics["total_revenue"] == Decimal("1750")
    assert metrics["ctr"] == 0.05
    assert metrics["cvr"] == 0.1
    assert metrics["roi"] == Decimal("4.0")  # (1750 - 350) / 350
    assert metrics["roas"] == Decimal("5.0")  # 1750 / 350


@pytest.mark.asyncio
async def test_get_listing_7day_metrics_custom_lookback(db_session):
    """Test get_listing_7day_metrics with custom lookback period."""
    # Create strategy run
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.MANUAL,
        status=StrategyRunStatus.COMPLETED,
    )
    db_session.add(strategy_run)

    # Create candidate
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.TEMU,
        title="Test Product",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    # Create listing
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
    )
    db_session.add(listing)
    await db_session.flush()

    # Create 14 days of performance data
    for i in range(14):
        perf = ListingPerformanceDaily(
            id=uuid4(),
            listing_id=listing.id,
            metric_date=date.today() - timedelta(days=i),
            impressions=1000,
            clicks=50,
            orders=5,
            units_sold=5,
            revenue=Decimal("250"),
            ad_spend=Decimal("50"),
        )
        db_session.add(perf)
    await db_session.flush()

    # Get 3-day metrics
    metrics = await PerformanceCalculator.get_listing_7day_metrics(db_session, listing.id, lookback_days=3)

    assert metrics is not None
    assert metrics["data_points"] == 3
    assert metrics["total_impressions"] == 3000
    assert metrics["total_clicks"] == 150
