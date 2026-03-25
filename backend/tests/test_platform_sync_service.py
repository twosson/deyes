"""Tests for platform sync service."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CandidateStatus,
    PlatformListingStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import CandidateProduct, ListingPerformanceDaily, PlatformListing, StrategyRun
from app.services.platforms.base import PlatformAdapter


async def _make_strategy_run(db_session: AsyncSession) -> StrategyRun:
    sr = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        started_at=None,
    )
    db_session.add(sr)
    await db_session.flush()
    return sr


async def _make_listing(
    db_session: AsyncSession,
    *,
    strategy_run: StrategyRun,
    platform_listing_id: str = "TEST-SKU-001",
    status: PlatformListingStatus = PlatformListingStatus.ACTIVE,
    price: Decimal = Decimal("19.99"),
    inventory: int = 50,
) -> PlatformListing:
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id=f"src-{uuid4().hex[:8]}",
        title="Sync Test Product",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)
    await db_session.flush()

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        platform_listing_id=platform_listing_id,
        price=price,
        currency="USD",
        inventory=inventory,
        status=status,
    )
    db_session.add(listing)
    await db_session.commit()
    await db_session.refresh(listing)
    return listing


def _make_mock_adapter() -> PlatformAdapter:
    """Create a mock adapter with in-memory listing state."""
    from unittest.mock import AsyncMock

    adapter = AsyncMock(spec=PlatformAdapter)
    adapter._state: dict[str, dict] = {}
    adapter._platform_listing_id = None

    async def mock_sync_inventory(platform_listing_id: str, new_inventory: int) -> bool:
        if platform_listing_id not in adapter._state:
            adapter._state[platform_listing_id] = {}
        adapter._state[platform_listing_id]["inventory"] = new_inventory
        return True

    async def mock_update_listing(
        platform_listing_id: str,
        price: Decimal | None = None,
        inventory: int | None = None,
        **kwargs,
    ) -> bool:
        if platform_listing_id not in adapter._state:
            adapter._state[platform_listing_id] = {}
        if price is not None:
            adapter._state[platform_listing_id]["price"] = str(price)
        if inventory is not None:
            adapter._state[platform_listing_id]["inventory"] = inventory
        return True

    async def mock_get_listing_status(platform_listing_id: str) -> dict:
        return adapter._state.get(platform_listing_id, {})

    adapter.sync_inventory = AsyncMock(side_effect=mock_sync_inventory)
    adapter.update_listing = AsyncMock(side_effect=mock_update_listing)
    adapter.get_listing_status = AsyncMock(side_effect=mock_get_listing_status)
    return adapter


# =============================================================================
# Inventory sync
# =============================================================================


@pytest.mark.asyncio
async def test_sync_listing_inventory_calls_adapter_with_local_inventory(db_session: AsyncSession):
    """sync_listing_inventory should push local DB inventory to the platform."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr, inventory=42)
    mock_adapter = _make_mock_adapter()

    def fake_get_adapter(platform, region):
        return mock_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        result = await service.sync_listing_inventory(db_session, listing_id=listing.id)

    assert result["status"] == "ok"
    assert result["inventory"] == 42
    mock_adapter.sync_inventory.assert_called_once_with(
        platform_listing_id="TEST-SKU-001",
        new_inventory=42,
    )


@pytest.mark.asyncio
async def test_sync_listing_inventory_stores_platform_data(db_session: AsyncSession):
    """sync_listing_inventory should merge sync metadata into platform_data."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr, inventory=10)

    def fake_get_adapter(platform, region):
        return _make_mock_adapter()

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        await service.sync_listing_inventory(db_session, listing_id=listing.id)

    await db_session.refresh(listing)
    assert "inventory_sync" in listing.platform_data
    assert listing.platform_data["inventory_sync"]["inventory"] == 10


@pytest.mark.asyncio
async def test_sync_listing_inventory_raises_on_missing_platform_listing_id(db_session: AsyncSession):
    """Missing platform_listing_id should raise ValueError."""
    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr, platform_listing_id="")
    listing.platform_listing_id = None
    await db_session.commit()

    from app.services.platform_sync_service import PlatformSyncService

    service = PlatformSyncService()
    with pytest.raises(ValueError, match="missing platform_listing_id"):
        await service.sync_listing_inventory(db_session, listing_id=listing.id)


@pytest.mark.asyncio
async def test_sync_listing_inventory_raises_on_adapter_failure(db_session: AsyncSession):
    """Adapter returning False should raise RuntimeError."""
    from unittest.mock import AsyncMock, patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr)

    broken_adapter = AsyncMock(spec=PlatformAdapter)
    broken_adapter.sync_inventory = AsyncMock(return_value=False)

    def fake_get_adapter(platform, region):
        return broken_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        with pytest.raises(RuntimeError, match="Failed to sync inventory"):
            await service.sync_listing_inventory(db_session, listing_id=listing.id)


# =============================================================================
# Price sync
# =============================================================================


@pytest.mark.asyncio
async def test_sync_listing_price_calls_adapter_with_listing_price(db_session: AsyncSession):
    """sync_listing_price should push local DB price to the platform."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr, price=Decimal("29.99"))
    mock_adapter = _make_mock_adapter()

    def fake_get_adapter(platform, region):
        return mock_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        result = await service.sync_listing_price(db_session, listing_id=listing.id)

    assert result["status"] == "ok"
    assert result["price"] == "29.99"
    mock_adapter.update_listing.assert_called_once_with(
        platform_listing_id="TEST-SKU-001",
        price=Decimal("29.99"),
    )


@pytest.mark.asyncio
async def test_sync_listing_price_stores_platform_data(db_session: AsyncSession):
    """sync_listing_price should merge sync metadata into platform_data."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr)

    def fake_get_adapter(platform, region):
        return _make_mock_adapter()

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        await service.sync_listing_price(db_session, listing_id=listing.id)

    await db_session.refresh(listing)
    assert "price_sync" in listing.platform_data
    assert listing.platform_data["price_sync"]["price"] == "19.99"


# =============================================================================
# Status sync
# =============================================================================


@pytest.mark.asyncio
async def test_sync_listing_status_updates_listing_from_remote_payload(db_session: AsyncSession):
    """sync_listing_status should update local listing fields from remote payload."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr, inventory=50)
    mock_adapter = _make_mock_adapter()
    mock_adapter._state["TEST-SKU-001"] = {
        "status": "active",
        "inventory": 30,
        "price": "25.99",
    }

    def fake_get_adapter(platform, region):
        return mock_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        result = await service.sync_listing_status(db_session, listing_id=listing.id)

    assert result["status"] == "ok"
    assert result["platform_status"] == PlatformListingStatus.ACTIVE.value
    assert result["inventory"] == 30
    assert result["price"] == "25.99"

    await db_session.refresh(listing)
    assert listing.inventory == 30
    assert listing.price == Decimal("25.99")
    assert listing.status == PlatformListingStatus.ACTIVE


@pytest.mark.asyncio
async def test_sync_listing_status_stores_raw_payload(db_session: AsyncSession):
    """sync_listing_status should preserve raw remote payload in platform_data."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr)
    mock_adapter = _make_mock_adapter()
    mock_adapter._state["TEST-SKU-001"] = {
        "status": "active",
        "inventory": 30,
        "price": "25.99",
        "views": 1000,
    }

    def fake_get_adapter(platform, region):
        return mock_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        await service.sync_listing_status(db_session, listing_id=listing.id)

    await db_session.refresh(listing)
    assert "status_sync" in listing.platform_data
    assert listing.platform_data["status_sync"]["status"] == "active"
    assert listing.platform_data["status_sync"]["inventory"] == 30


@pytest.mark.asyncio
async def test_sync_listing_status_maps_remote_status_to_out_of_stock(db_session: AsyncSession):
    """If remote status is missing but inventory is 0, listing should be OUT_OF_STOCK."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr)
    mock_adapter = _make_mock_adapter()
    mock_adapter._state["TEST-SKU-001"] = {
        "status": "active",
        "inventory": 0,
    }

    def fake_get_adapter(platform, region):
        return mock_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        result = await service.sync_listing_status(db_session, listing_id=listing.id)

    assert result["platform_status"] == PlatformListingStatus.OUT_OF_STOCK.value
    await db_session.refresh(listing)
    assert listing.status == PlatformListingStatus.OUT_OF_STOCK


@pytest.mark.asyncio
async def test_sync_listing_status_raises_on_empty_payload(db_session: AsyncSession):
    """Empty status payload should raise RuntimeError."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr)
    mock_adapter = _make_mock_adapter()
    mock_adapter._state["TEST-SKU-001"] = {}

    def fake_get_adapter(platform, region):
        return mock_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        with pytest.raises(RuntimeError, match="Failed to fetch status"):
            await service.sync_listing_status(db_session, listing_id=listing.id)


# =============================================================================
# Metrics sync
# =============================================================================


@pytest.mark.asyncio
async def test_sync_listing_metrics_records_one_daily_row(db_session: AsyncSession):
    """sync_listing_metrics should persist a single ListingPerformanceDaily row."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr)
    mock_adapter = _make_mock_adapter()
    sync_date = date.today()
    mock_adapter._state["TEST-SKU-001"] = {
        "status": "active",
        "inventory": 30,
        "views": 1500,
        "clicks": 75,
        "sales": 10,
    }

    def fake_get_adapter(platform, region):
        return mock_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        result = await service.sync_listing_metrics(
            db_session,
            listing_id=listing.id,
            start_date=sync_date,
            end_date=sync_date,
        )

    assert result["status"] == "ok"
    assert result["synced_days"] == 1
    assert result["end_date"] == str(sync_date)

    stmt = select(ListingPerformanceDaily).where(
        ListingPerformanceDaily.listing_id == listing.id,
        ListingPerformanceDaily.metric_date == sync_date,
    )
    result_row = await db_session.execute(stmt)
    row = result_row.scalar_one_or_none()
    assert row is not None
    assert row.impressions == 1500
    assert row.clicks == 75
    assert row.orders == 10
    assert row.units_sold == 10


@pytest.mark.asyncio
async def test_sync_listing_metrics_stores_raw_payload(db_session: AsyncSession):
    """sync_listing_metrics should store raw adapter payload in the daily record."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr)
    mock_adapter = _make_mock_adapter()
    mock_adapter._state["TEST-SKU-001"] = {
        "status": "active",
        "views": 500,
        "sales": 5,
    }

    def fake_get_adapter(platform, region):
        return mock_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        await service.sync_listing_metrics(
            db_session,
            listing_id=listing.id,
            start_date=date.today(),
            end_date=date.today(),
        )

    stmt = select(ListingPerformanceDaily).where(
        ListingPerformanceDaily.listing_id == listing.id,
        ListingPerformanceDaily.metric_date == date.today(),
    )
    result_row = await db_session.execute(stmt)
    row = result_row.scalar_one_or_none()
    assert row is not None
    assert row.raw_payload["views"] == 500
    assert row.raw_payload["sales"] == 5


@pytest.mark.asyncio
async def test_sync_listing_metrics_returns_no_data_on_empty_payload(db_session: AsyncSession):
    """Empty status payload should return no_data status without persisting a row."""
    from unittest.mock import patch

    sr = await _make_strategy_run(db_session)
    listing = await _make_listing(db_session, strategy_run=sr)
    mock_adapter = _make_mock_adapter()
    mock_adapter._state["TEST-SKU-001"] = {}

    def fake_get_adapter(platform, region):
        return mock_adapter

    with patch("app.services.platform_sync_service.get_platform_adapter", fake_get_adapter):
        from app.services.platform_sync_service import PlatformSyncService

        service = PlatformSyncService()
        result = await service.sync_listing_metrics(
            db_session,
            listing_id=listing.id,
            start_date=date.today(),
            end_date=date.today(),
        )

    assert result["status"] == "no_data"
    assert result["synced_days"] == 0

    stmt = select(ListingPerformanceDaily).where(
        ListingPerformanceDaily.listing_id == listing.id,
        ListingPerformanceDaily.metric_date == date.today(),
    )
    result_row = await db_session.execute(stmt)
    row = result_row.scalar_one_or_none()
    assert row is None


# =============================================================================
# Asset performance stub
# =============================================================================


@pytest.mark.asyncio
async def test_sync_asset_performance_still_returns_stub(db_session: AsyncSession):
    """Asset performance sync remains a stub; no implementation required."""
    from app.services.platform_sync_service import PlatformSyncService

    service = PlatformSyncService()
    result = await service.sync_asset_performance(
        db_session,
        asset_id=uuid4(),
        listing_id=uuid4(),
        start_date=date.today(),
        end_date=date.today(),
    )

    assert result["status"] == "stub_not_implemented"
    assert result["synced_days"] == 0
