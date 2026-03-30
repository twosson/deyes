"""Unified listing service for cross-platform operations.

Provides a unified entry point for creating, updating, syncing, and querying
platform listings across multiple platforms and regions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PlatformListingStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import CandidateProduct, ContentAsset, InventorySyncLog, PlatformListing
from app.services.listing_activation_service import ListingActivationService
from app.services.platform_policy_service import PlatformPolicyService
from app.services.platform_registry import get_platform_registry
from app.services.platform_sync_service import PlatformSyncService


class UnifiedListingService:
    """Unified listing service for cross-platform operations.

    Provides a single entry point for:
    - Creating listings on platforms via adapters
    - Updating listing attributes
    - Syncing listing status from platforms
    - Querying listings across platforms
    """

    def __init__(self):
        self.logger = get_logger(__name__)
        self.registry = get_platform_registry()
        self.activation_service = ListingActivationService()
        self.sync_service = PlatformSyncService()
        self.policy_service = PlatformPolicyService()

    async def create_listing(
        self,
        db: AsyncSession,
        *,
        platform: TargetPlatform | str,
        region: str,
        marketplace: str | None,
        product_variant_id: UUID | None,
        candidate_product_id: UUID,
        payload: dict[str, Any],
    ) -> PlatformListing:
        """Create listing on platform via adapter.

        Args:
            db: Database session
            platform: Target platform (enum or string)
            region: Region code (e.g., "us", "uk")
            marketplace: Marketplace identifier (e.g., "amazon_us", optional)
            product_variant_id: Product variant ID (SKU)
            candidate_product_id: Candidate product ID
            payload: Listing payload with:
                - price: Decimal
                - currency: str
                - inventory: int
                - title: str (optional)
                - description: str (optional)
                - category: str (optional)
                - assets: list[ContentAsset]
                - inventory_mode: InventoryMode (optional)

        Returns:
            Created PlatformListing instance

        Raises:
            ValueError: If platform not supported or payload invalid
        """
        platform_enum = platform if isinstance(platform, TargetPlatform) else TargetPlatform(platform)

        self.logger.info(
            "unified_listing_create_started",
            platform=platform_enum.value,
            region=region,
            marketplace=marketplace,
            candidate_product_id=str(candidate_product_id),
        )

        # Validate platform capability
        if not self.registry.supports_feature(platform_enum, "create_listing"):
            raise ValueError(f"Platform {platform_enum.value} does not support listing creation")

        # Get platform adapter
        adapter = self.registry.get_adapter(platform_enum, region)

        # Get candidate product
        candidate = await db.get(CandidateProduct, candidate_product_id)
        if not candidate:
            raise ValueError(f"Candidate product not found: {candidate_product_id}")

        # Extract payload fields
        price = payload.get("price")
        currency = payload.get("currency", "USD")
        inventory = payload.get("inventory", 0)
        title = payload.get("title")
        description = payload.get("description")
        category = payload.get("category")
        assets = payload.get("assets", [])
        inventory_mode = payload.get("inventory_mode")

        if not price:
            raise ValueError("Price is required in payload")

        # Resolve platform category mapping
        category_resolution = await self._resolve_platform_category(
            db=db,
            platform=platform_enum,
            region=region,
            category=category,
        )

        # Call adapter to create listing
        listing_data = await adapter.create_listing(
            product=candidate,
            assets=assets,
            region=region,
            price=Decimal(str(price)),
            currency=currency,
            inventory=inventory,
            title=title,
            description=description,
            category=category_resolution["category"],
            category_id=category_resolution["category_id"],
            category_name=category_resolution["category_name"],
        )

        # Create PlatformListing record
        listing = PlatformListing(
            id=uuid4(),
            candidate_product_id=candidate_product_id,
            product_variant_id=product_variant_id,
            inventory_mode=inventory_mode,
            platform=platform_enum,
            region=region,
            marketplace=marketplace,
            platform_listing_id=listing_data.platform_listing_id,
            platform_url=listing_data.platform_url,
            price=Decimal(str(price)),
            currency=currency,
            inventory=inventory,
            status=PlatformListingStatus.PENDING,
            platform_data=listing_data.platform_data,
        )

        db.add(listing)
        await db.flush()

        # Check activation eligibility
        activated, reason = await self.activation_service.activate_listing_if_eligible(
            db=db,
            listing_id=listing.id,
        )

        if activated:
            self.logger.info(
                "unified_listing_activated",
                listing_id=str(listing.id),
                platform=platform_enum.value,
                region=region,
            )
        else:
            self.logger.warning(
                "unified_listing_activation_deferred",
                listing_id=str(listing.id),
                platform=platform_enum.value,
                region=region,
                reason=reason,
            )

        # Record sync log
        await self._record_sync_log(
            db=db,
            listing_id=listing.id,
            action="create_listing",
            success=True,
        )

        await db.commit()

        self.logger.info(
            "unified_listing_create_completed",
            listing_id=str(listing.id),
            platform=platform_enum.value,
            region=region,
            platform_listing_id=listing_data.platform_listing_id,
        )

        return listing

    async def update_listing(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
        payload: dict[str, Any],
    ) -> PlatformListing:
        """Update listing on platform via adapter.

        Args:
            db: Database session
            listing_id: Listing ID to update
            payload: Update payload with optional fields:
                - price: Decimal
                - inventory: int
                - title: str
                - description: str

        Returns:
            Updated PlatformListing instance

        Raises:
            ValueError: If listing not found or update fails
        """
        listing = await db.get(PlatformListing, listing_id)
        if not listing:
            raise ValueError(f"Listing not found: {listing_id}")

        self.logger.info(
            "unified_listing_update_started",
            listing_id=str(listing_id),
            platform=listing.platform.value,
            region=listing.region,
        )

        # Validate platform capability
        if not self.registry.supports_feature(listing.platform, "update_listing"):
            raise ValueError(f"Platform {listing.platform.value} does not support listing updates")

        # Get platform adapter
        adapter = self.registry.get_adapter(listing.platform, listing.region)

        # Extract update fields
        price = payload.get("price")
        inventory = payload.get("inventory")
        title = payload.get("title")
        description = payload.get("description")

        # Call adapter to update listing
        success = await adapter.update_listing(
            platform_listing_id=listing.platform_listing_id,
            price=Decimal(str(price)) if price else None,
            inventory=inventory,
            title=title,
            description=description,
        )

        if not success:
            await self._record_sync_log(
                db=db,
                listing_id=listing_id,
                action="update_listing",
                success=False,
                error="Adapter update failed",
            )
            raise ValueError(f"Failed to update listing {listing_id} on platform")

        # Update local record
        if price is not None:
            listing.price = Decimal(str(price))
        if inventory is not None:
            listing.inventory = inventory

        listing.last_synced_at = datetime.now(timezone.utc)

        await db.flush()

        # Record sync log
        await self._record_sync_log(
            db=db,
            listing_id=listing_id,
            action="update_listing",
            success=True,
        )

        await db.commit()

        self.logger.info(
            "unified_listing_update_completed",
            listing_id=str(listing_id),
            platform=listing.platform.value,
            region=listing.region,
        )

        return listing

    async def sync_listing(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
    ) -> PlatformListing:
        """Sync listing status from platform.

        Args:
            db: Database session
            listing_id: Listing ID to sync

        Returns:
            Updated PlatformListing instance

        Raises:
            ValueError: If listing not found or sync fails
        """
        listing = await db.get(PlatformListing, listing_id)
        if not listing:
            raise ValueError(f"Listing not found: {listing_id}")

        self.logger.info(
            "unified_listing_sync_started",
            listing_id=str(listing_id),
            platform=listing.platform.value,
            region=listing.region,
        )

        try:
            # Use existing sync service
            await self.sync_service.sync_listing_status(
                db=db,
                listing_id=listing_id,
            )

            # Record sync log
            await self._record_sync_log(
                db=db,
                listing_id=listing_id,
                action="sync_listing",
                success=True,
            )

            await db.commit()

            self.logger.info(
                "unified_listing_sync_completed",
                listing_id=str(listing_id),
                platform=listing.platform.value,
                region=listing.region,
                status=listing.status.value,
            )

            return listing

        except Exception as e:
            await self._record_sync_log(
                db=db,
                listing_id=listing_id,
                action="sync_listing",
                success=False,
                error=str(e),
            )
            raise

    async def get_listing_snapshot(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
    ) -> dict[str, Any]:
        """Get unified listing snapshot.

        Args:
            db: Database session
            listing_id: Listing ID

        Returns:
            Unified listing snapshot dict

        Raises:
            ValueError: If listing not found
        """
        listing = await db.get(PlatformListing, listing_id)
        if not listing:
            raise ValueError(f"Listing not found: {listing_id}")

        return self._build_listing_snapshot(listing)

    async def get_sku_listings(
        self,
        db: AsyncSession,
        *,
        product_variant_id: UUID,
    ) -> list[PlatformListing]:
        """Get all listings for a SKU across platforms.

        Args:
            db: Database session
            product_variant_id: Product variant ID (SKU)

        Returns:
            List of PlatformListing instances
        """
        stmt = select(PlatformListing).where(
            PlatformListing.product_variant_id == product_variant_id
        )
        result = await db.execute(stmt)
        listings = list(result.scalars().all())

        self.logger.info(
            "unified_listing_sku_query",
            product_variant_id=str(product_variant_id),
            listing_count=len(listings),
        )

        return listings

    async def get_platform_listings(
        self,
        db: AsyncSession,
        *,
        platform: TargetPlatform | str,
        region: str | None = None,
        status: PlatformListingStatus | None = None,
    ) -> list[PlatformListing]:
        """Get all listings for a platform/region.

        Args:
            db: Database session
            platform: Target platform (enum or string)
            region: Region code (optional filter)
            status: Status filter (optional)

        Returns:
            List of PlatformListing instances
        """
        platform_enum = platform if isinstance(platform, TargetPlatform) else TargetPlatform(platform)

        stmt = select(PlatformListing).where(PlatformListing.platform == platform_enum)

        if region:
            stmt = stmt.where(PlatformListing.region == region)
        if status:
            stmt = stmt.where(PlatformListing.status == status)

        result = await db.execute(stmt)
        listings = list(result.scalars().all())

        self.logger.info(
            "unified_listing_platform_query",
            platform=platform_enum.value,
            region=region,
            status=status.value if status else None,
            listing_count=len(listings),
        )

        return listings

    async def _resolve_platform_category(
        self,
        *,
        db: AsyncSession,
        platform: TargetPlatform,
        region: str,
        category: str | None,
    ) -> dict[str, Any]:
        """Resolve platform category mapping from policy.

        Returns:
            {
                "category": str | None,           # Original category
                "category_id": str | int | None,  # Mapped platform category id
                "category_name": str | None,      # Mapped platform category name
                "mapping_source": str,            # "policy" | "fallback" | "passthrough"
            }
        """
        if not category:
            return {
                "category": None,
                "category_id": None,
                "category_name": None,
                "mapping_source": "passthrough",
            }

        # Query policy mapping
        mapping = await self.policy_service.get_category_mapping(
            db=db,
            platform=platform,
            internal_category=category,
            region=region,
        )

        if mapping:
            self.logger.info(
                "category_mapping_resolved",
                platform=platform.value,
                region=region,
                internal_category=category,
                platform_category_id=mapping.platform_category_id,
                mapping_source="policy",
            )
            return {
                "category": category,
                "category_id": mapping.platform_category_id,
                "category_name": mapping.platform_category_name,
                "mapping_source": "policy",
            }

        # Fallback: passthrough original category
        self.logger.info(
            "category_mapping_fallback",
            platform=platform.value,
            region=region,
            internal_category=category,
            mapping_source="fallback",
        )
        return {
            "category": category,
            "category_id": None,
            "category_name": None,
            "mapping_source": "fallback",
        }

    def _build_listing_snapshot(self, listing: PlatformListing) -> dict[str, Any]:
        """Build unified listing snapshot structure.

        Args:
            listing: PlatformListing instance

        Returns:
            Unified snapshot dict
        """
        return {
            "listing_id": str(listing.id),
            "platform": listing.platform.value,
            "region": listing.region,
            "marketplace": listing.marketplace,
            "product_variant_id": str(listing.product_variant_id) if listing.product_variant_id else None,
            "candidate_product_id": str(listing.candidate_product_id),
            "status": listing.status.value,
            "price": float(listing.price),
            "currency": listing.currency,
            "inventory": listing.inventory,
            "inventory_mode": listing.inventory_mode.value if listing.inventory_mode else None,
            "platform_listing_id": listing.platform_listing_id,
            "platform_url": listing.platform_url,
            "last_synced_at": listing.last_synced_at.isoformat() if listing.last_synced_at else None,
            "created_at": listing.created_at.isoformat() if hasattr(listing, "created_at") else None,
            "updated_at": listing.updated_at.isoformat() if hasattr(listing, "updated_at") else None,
        }

    async def _record_sync_log(
        self,
        db: AsyncSession,
        *,
        listing_id: UUID,
        action: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Record sync operation log.

        Args:
            db: Database session
            listing_id: Listing ID
            action: Action name (e.g., "create_listing", "sync_listing")
            success: Whether operation succeeded
            error: Error message if failed
        """
        log = InventorySyncLog(
            id=uuid4(),
            listing_id=listing_id,
            old_inventory=0,  # Not applicable for general sync log
            new_inventory=0,  # Not applicable for general sync log
            sync_status="success" if success else "failed",
            error_message=error,
            synced_at=datetime.now(timezone.utc),
        )
        db.add(log)
        await db.flush()


__all__ = ["UnifiedListingService"]
