"""Platform sync service for listing and asset performance backfill."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PlatformListingStatus
from app.core.logging import get_logger
from app.db.models import PlatformListing
from app.services.listing_metrics_service import ListingMetricsService
from app.services.platforms import get_platform_adapter


class PlatformSyncService:
    """Service for syncing marketplace performance data."""

    def __init__(self):
        self.logger = get_logger(__name__)
        self.metrics_service = ListingMetricsService()

    async def sync_listing_metrics(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
        start_date: date,
        end_date: date,
    ) -> dict:
        """Sync listing metrics for the requested date range.

        Fetches current counters from the platform adapter and persists a truthful
        snapshot for end_date only. Does not fabricate historical data.
        """
        listing = await self._load_and_validate_listing(db, listing_id)
        adapter = get_platform_adapter(listing.platform, listing.region)

        status_payload = await adapter.get_listing_status(
            platform_listing_id=listing.platform_listing_id
        )

        if not status_payload or not self._has_metrics_payload(status_payload):
            self.logger.warning(
                "platform_sync_listing_metrics_empty_payload",
                listing_id=str(listing_id),
            )
            return {
                "listing_id": str(listing_id),
                "start_date": str(start_date),
                "end_date": str(end_date),
                "synced_days": 0,
                "status": "no_data",
            }

        impressions = self._coerce_int(
            status_payload.get("impressions", status_payload.get("views")),
            0,
        )
        clicks = self._coerce_int(status_payload.get("clicks"), 0)
        orders = self._coerce_int(
            status_payload.get("orders", status_payload.get("sales")),
            0,
        )
        units_sold = self._coerce_int(
            status_payload.get("units_sold", status_payload.get("sales")),
            0,
        )
        revenue = self._coerce_decimal(status_payload.get("revenue"))

        await self.metrics_service.record_daily_metrics(
            db,
            listing_id=listing_id,
            metric_date=end_date,
            impressions=impressions,
            clicks=clicks,
            orders=orders,
            units_sold=units_sold,
            revenue=revenue,
            raw_payload=self._json_safe(status_payload),
        )

        self.logger.info(
            "platform_sync_listing_metrics_completed",
            listing_id=str(listing_id),
            metric_date=str(end_date),
            impressions=impressions,
            orders=orders,
        )

        return {
            "listing_id": str(listing_id),
            "start_date": str(start_date),
            "end_date": str(end_date),
            "synced_days": 1,
            "status": "ok",
        }

    async def sync_listing_status(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
    ) -> dict:
        """Sync listing status from remote platform.

        Fetches remote status/inventory/price and updates local PlatformListing fields.
        """
        listing = await self._load_and_validate_listing(db, listing_id)
        adapter = get_platform_adapter(listing.platform, listing.region)

        status_payload = await adapter.get_listing_status(
            platform_listing_id=listing.platform_listing_id
        )

        if not status_payload:
            raise RuntimeError(f"Failed to fetch status for listing {listing_id}")

        remote_status_str = status_payload.get("status")
        normalized_status = self._normalize_platform_status(remote_status_str)

        remote_inventory = self._coerce_int(status_payload.get("inventory"), None)
        remote_price = self._coerce_decimal(status_payload.get("price"))

        if remote_inventory == 0 and normalized_status not in {
            PlatformListingStatus.DELISTED,
            PlatformListingStatus.REJECTED,
        }:
            listing.status = PlatformListingStatus.OUT_OF_STOCK
        elif normalized_status is not None:
            listing.status = normalized_status

        if remote_inventory is not None:
            listing.inventory = remote_inventory
        if remote_price is not None:
            listing.price = remote_price

        listing.platform_data = self._merge_platform_payload(
            listing.platform_data,
            self._json_safe(status_payload),
            "status_sync",
        )

        await db.flush()

        self.logger.info(
            "platform_sync_listing_status_completed",
            listing_id=str(listing_id),
            status=listing.status.value,
            inventory=listing.inventory,
            price=str(listing.price),
        )

        return {
            "listing_id": str(listing_id),
            "status": "ok",
            "platform_status": listing.status.value,
            "inventory": listing.inventory,
            "price": str(listing.price),
        }

    async def sync_listing_inventory(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
    ) -> dict:
        """Sync inventory to remote platform.

        Treats local DB inventory as source of truth and pushes to platform.
        """
        listing = await self._load_and_validate_listing(db, listing_id)
        adapter = get_platform_adapter(listing.platform, listing.region)

        success = await adapter.sync_inventory(
            platform_listing_id=listing.platform_listing_id,
            new_inventory=listing.inventory,
        )

        if not success:
            raise RuntimeError(f"Failed to sync inventory for listing {listing_id}")

        listing.platform_data = self._merge_platform_payload(
            listing.platform_data,
            {"inventory": listing.inventory, "synced_at": str(date.today())},
            "inventory_sync",
        )

        await db.flush()

        self.logger.info(
            "platform_sync_listing_inventory_completed",
            listing_id=str(listing_id),
            inventory=listing.inventory,
        )

        return {
            "listing_id": str(listing_id),
            "status": "ok",
            "inventory": listing.inventory,
        }

    async def sync_listing_price(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
    ) -> dict:
        """Sync price to remote platform.

        Treats local DB price as source of truth and pushes to platform.
        """
        listing = await self._load_and_validate_listing(db, listing_id)
        adapter = get_platform_adapter(listing.platform, listing.region)

        success = await adapter.update_listing(
            platform_listing_id=listing.platform_listing_id,
            price=listing.price,
        )

        if not success:
            raise RuntimeError(f"Failed to sync price for listing {listing_id}")

        listing.platform_data = self._merge_platform_payload(
            listing.platform_data,
            {"price": str(listing.price), "synced_at": str(date.today())},
            "price_sync",
        )

        await db.flush()

        self.logger.info(
            "platform_sync_listing_price_completed",
            listing_id=str(listing_id),
            price=str(listing.price),
        )

        return {
            "listing_id": str(listing_id),
            "status": "ok",
            "price": str(listing.price),
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
        """Stub implementation for asset performance sync.

        Deferred until platform adapters expose asset-level metrics.
        """
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

    async def _load_and_validate_listing(
        self, db: AsyncSession, listing_id: UUID
    ) -> PlatformListing:
        """Load listing and validate required fields for sync."""
        listing = await db.get(PlatformListing, listing_id)
        if not listing:
            raise ValueError(f"Listing not found: {listing_id}")

        if not listing.platform_listing_id:
            raise ValueError(
                f"Listing {listing_id} missing platform_listing_id; cannot sync"
            )

        return listing

    def _normalize_platform_status(self, status_str: str | None) -> PlatformListingStatus | None:
        """Map remote platform status string to internal enum."""
        if not status_str:
            return None

        status_lower = status_str.lower()
        mapping = {
            "active": PlatformListingStatus.ACTIVE,
            "online": PlatformListingStatus.ACTIVE,
            "paused": PlatformListingStatus.PAUSED,
            "offline": PlatformListingStatus.PAUSED,
            "out_of_stock": PlatformListingStatus.OUT_OF_STOCK,
            "sold_out": PlatformListingStatus.OUT_OF_STOCK,
            "deleted": PlatformListingStatus.DELISTED,
            "delisted": PlatformListingStatus.DELISTED,
            "rejected": PlatformListingStatus.REJECTED,
        }
        return mapping.get(status_lower)

    def _coerce_int(self, value: Any, default: int = 0) -> int:
        """Coerce value to int, returning default if None or invalid."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _coerce_decimal(self, value: Any) -> Decimal | None:
        """Coerce value to Decimal, returning None if invalid."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (ValueError, TypeError):
            return None

    def _json_safe(self, payload: dict) -> dict:
        """Convert payload to JSON-safe dict."""
        result = {}
        for k, v in payload.items():
            if isinstance(v, Decimal):
                result[k] = str(v)
            else:
                result[k] = v
        return result

    def _merge_platform_payload(
        self, existing: dict | None, new_data: dict, sync_key: str
    ) -> dict:
        """Merge new sync payload into existing platform_data without losing history."""
        merged = existing.copy() if existing else {}
        merged[sync_key] = new_data
        return merged

    def _has_metrics_payload(self, payload: dict) -> bool:
        """Check if payload contains at least one usable metric counter."""
        metric_keys = ["views", "impressions", "clicks", "sales", "orders", "units_sold", "revenue"]
        return any(payload.get(k) is not None for k in metric_keys)
