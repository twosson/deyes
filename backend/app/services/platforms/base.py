"""Platform adapter base classes and interfaces.

Defines the common interface for all platform adapters (Temu, Amazon, Ozon, etc.)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.enums import PlatformListingStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import CandidateProduct, ContentAsset


class PlatformListingData:
    """Data structure for platform listing."""

    def __init__(
        self,
        *,
        platform_listing_id: str,
        platform_url: str | None = None,
        status: PlatformListingStatus = PlatformListingStatus.ACTIVE,
        platform_data: dict[str, Any] | None = None,
    ):
        self.platform_listing_id = platform_listing_id
        self.platform_url = platform_url
        self.status = status
        self.platform_data = platform_data or {}


class PlatformAdapter(ABC):
    """Base class for platform adapters.

    Each platform (Temu, Amazon, Ozon, etc.) should implement this interface.
    """

    def __init__(self, platform: TargetPlatform):
        self.platform = platform
        self.logger = get_logger(f"{__name__}.{platform.value}")

    @abstractmethod
    async def create_listing(
        self,
        *,
        product: CandidateProduct,
        assets: list[ContentAsset],
        region: str,
        price: Decimal,
        currency: str,
        inventory: int,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
        attributes: dict[str, Any] | None = None,
        category_id: str | int | None = None,
        category_name: str | None = None,
        platform_context: dict[str, Any] | None = None,
    ) -> PlatformListingData:
        """Create a new listing on the platform.

        Args:
            product: Candidate product
            assets: Content assets (images)
            region: Target region (e.g., "us", "uk")
            price: Listing price
            currency: Currency code (e.g., "USD")
            inventory: Initial inventory
            title: Custom title (optional, uses product.title if None)
            description: Product description
            category: Internal category name
            attributes: Platform-specific attributes
            category_id: Resolved platform category ID from policy mapping (optional)
            category_name: Resolved platform category name from policy mapping (optional)
            platform_context: Additional platform-specific context (optional)

        Returns:
            PlatformListingData with platform listing ID and status
        """
        pass

    @abstractmethod
    async def update_listing(
        self,
        *,
        platform_listing_id: str,
        price: Decimal | None = None,
        inventory: int | None = None,
        title: str | None = None,
        description: str | None = None,
        images: list[str] | None = None,
        status: PlatformListingStatus | None = None,
    ) -> bool:
        """Update an existing listing.

        Args:
            platform_listing_id: Platform's listing ID
            price: New price (optional)
            inventory: New inventory (optional)
            title: New title (optional)
            description: New description (optional)
            images: New image URLs (optional)
            status: New status (optional)

        Returns:
            True if update successful
        """
        pass

    @abstractmethod
    async def sync_inventory(
        self,
        *,
        platform_listing_id: str,
        new_inventory: int,
    ) -> bool:
        """Sync inventory to platform.

        Args:
            platform_listing_id: Platform's listing ID
            new_inventory: New inventory count

        Returns:
            True if sync successful
        """
        pass

    @abstractmethod
    async def get_listing_status(
        self,
        *,
        platform_listing_id: str,
    ) -> dict[str, Any]:
        """Get current listing status from platform.

        Args:
            platform_listing_id: Platform's listing ID

        Returns:
            Dict with status, inventory, price, etc.
        """
        pass

    @abstractmethod
    async def delist_product(
        self,
        *,
        platform_listing_id: str,
    ) -> bool:
        """Remove listing from platform.

        Args:
            platform_listing_id: Platform's listing ID

        Returns:
            True if delisting successful
        """
        pass

    async def validate_listing_data(
        self,
        *,
        product: CandidateProduct,
        assets: list[ContentAsset],
        region: str,
        price: Decimal,
    ) -> tuple[bool, str | None]:
        """Validate listing data before submission.

        Args:
            product: Candidate product
            assets: Content assets
            region: Target region
            price: Listing price

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Basic validation
        if not product.title:
            return False, "Product title is required"

        if not assets:
            return False, "At least one image is required"

        if price <= 0:
            return False, "Price must be positive"

        # Platform-specific validation can be overridden
        return True, None

    def map_category(self, internal_category: str | None) -> str | None:
        """Map internal category to platform category.

        Override this method for platform-specific category mapping.
        """
        return internal_category

    def format_title(self, title: str, max_length: int = 200) -> str:
        """Format title according to platform requirements.

        Args:
            title: Original title
            max_length: Maximum allowed length

        Returns:
            Formatted title
        """
        if len(title) <= max_length:
            return title
        return title[:max_length - 3] + "..."

    def format_price(self, price: Decimal, currency: str) -> str:
        """Format price according to platform requirements.

        Args:
            price: Price value
            currency: Currency code

        Returns:
            Formatted price string
        """
        return f"{price:.2f}"


class MockPlatformAdapter(PlatformAdapter):
    """Mock adapter for testing."""

    def __init__(self, platform: TargetPlatform):
        super().__init__(platform)
        self._listings: dict[str, dict] = {}

    async def create_listing(
        self,
        *,
        product: CandidateProduct,
        assets: list[ContentAsset],
        region: str,
        price: Decimal,
        currency: str,
        inventory: int,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
        attributes: dict[str, Any] | None = None,
        category_id: str | int | None = None,
        category_name: str | None = None,
        platform_context: dict[str, Any] | None = None,
    ) -> PlatformListingData:
        """Mock create listing."""
        import uuid

        listing_id = f"MOCK-{uuid.uuid4().hex[:12].upper()}"
        listing_url = f"https://mock-{self.platform.value}.com/product/{listing_id}"

        self._listings[listing_id] = {
            "product_id": str(product.id),
            "title": title or product.title,
            "price": float(price),
            "currency": currency,
            "inventory": inventory,
            "status": "active",
            "images": [asset.file_url for asset in assets],
        }

        self.logger.info(
            "mock_listing_created",
            platform=self.platform.value,
            listing_id=listing_id,
            product_id=str(product.id),
        )

        return PlatformListingData(
            platform_listing_id=listing_id,
            platform_url=listing_url,
            status=PlatformListingStatus.ACTIVE,
            platform_data=self._listings[listing_id],
        )

    async def update_listing(
        self,
        *,
        platform_listing_id: str,
        price: Decimal | None = None,
        inventory: int | None = None,
        title: str | None = None,
        description: str | None = None,
        images: list[str] | None = None,
        status: PlatformListingStatus | None = None,
    ) -> bool:
        """Mock update listing."""
        if platform_listing_id not in self._listings:
            return False

        listing = self._listings[platform_listing_id]
        if price is not None:
            listing["price"] = float(price)
        if inventory is not None:
            listing["inventory"] = inventory
        if title is not None:
            listing["title"] = title
        if images is not None:
            listing["images"] = images
        if status is not None:
            listing["status"] = status.value

        return True

    async def sync_inventory(
        self,
        *,
        platform_listing_id: str,
        new_inventory: int,
    ) -> bool:
        """Mock sync inventory."""
        return await self.update_listing(
            platform_listing_id=platform_listing_id,
            inventory=new_inventory,
        )

    async def get_listing_status(
        self,
        *,
        platform_listing_id: str,
    ) -> dict[str, Any]:
        """Mock get listing status."""
        if platform_listing_id in self._listings:
            return self._listings[platform_listing_id]
        return {}

    async def delist_product(
        self,
        *,
        platform_listing_id: str,
    ) -> bool:
        """Mock delist product."""
        return await self.update_listing(
            platform_listing_id=platform_listing_id,
            status=PlatformListingStatus.DELISTED,
        )
