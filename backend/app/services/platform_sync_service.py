"""Platform sync service stubs for listing and asset performance backfill."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger


class PlatformSyncService:
    """Stub service for syncing marketplace performance data."""

    def __init__(self):
        self.logger = get_logger(__name__)

    async def sync_listing_metrics(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
        start_date: date,
        end_date: date,
    ) -> dict:
        """Stub implementation for listing metrics sync."""
        self.logger.info(
            "platform_sync_listing_metrics_stub_called",
            listing_id=str(listing_id),
            start_date=str(start_date),
            end_date=str(end_date),
        )
        return {
            "listing_id": str(listing_id),
            "start_date": str(start_date),
            "end_date": str(end_date),
            "synced_days": 0,
            "status": "stub_not_implemented",
        }

    async def sync_asset_performance(
        self,
        db: AsyncSession,
        *,
        asset_id: UUID,
        listing_id: UUID,
        start_date: date,
        end_date: date,
    ) -> dict:
        """Stub implementation for asset performance sync."""
        self.logger.info(
            "platform_sync_asset_performance_stub_called",
            asset_id=str(asset_id),
            listing_id=str(listing_id),
            start_date=str(start_date),
            end_date=str(end_date),
        )
        return {
            "asset_id": str(asset_id),
            "listing_id": str(listing_id),
            "start_date": str(start_date),
            "end_date": str(end_date),
            "synced_days": 0,
            "status": "stub_not_implemented",
        }
