"""Tests for platform sync service stub."""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_sync_service import PlatformSyncService


@pytest.mark.asyncio
async def test_sync_listing_metrics_stub(db_session: AsyncSession):
    """PlatformSyncService.sync_listing_metrics should return stub response."""
    service = PlatformSyncService()
    listing_id = uuid4()
    start_date = date.today() - timedelta(days=7)
    end_date = date.today()

    result = await service.sync_listing_metrics(
        db_session,
        listing_id=listing_id,
        start_date=start_date,
        end_date=end_date,
    )

    assert result["listing_id"] == str(listing_id)
    assert result["start_date"] == str(start_date)
    assert result["end_date"] == str(end_date)
    assert result["synced_days"] == 0
    assert result["status"] == "stub_not_implemented"


@pytest.mark.asyncio
async def test_sync_asset_performance_stub(db_session: AsyncSession):
    """PlatformSyncService.sync_asset_performance should return stub response."""
    service = PlatformSyncService()
    asset_id = uuid4()
    listing_id = uuid4()
    start_date = date.today() - timedelta(days=7)
    end_date = date.today()

    result = await service.sync_asset_performance(
        db_session,
        asset_id=asset_id,
        listing_id=listing_id,
        start_date=start_date,
        end_date=end_date,
    )

    assert result["asset_id"] == str(asset_id)
    assert result["listing_id"] == str(listing_id)
    assert result["start_date"] == str(start_date)
    assert result["end_date"] == str(end_date)
    assert result["synced_days"] == 0
    assert result["status"] == "stub_not_implemented"
