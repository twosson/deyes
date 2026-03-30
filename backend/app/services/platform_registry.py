"""Platform adapter registry and resolver.

Provides centralized platform adapter registration, capability management,
and runtime resolution for multi-platform operations.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.enums import TargetPlatform
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.services.platforms.base import PlatformAdapter


class PlatformCapability:
    """Platform capability constants."""

    CREATE_LISTING = "create_listing"
    UPDATE_LISTING = "update_listing"
    SYNC_INVENTORY = "sync_inventory"
    SYNC_PRICE = "sync_price"
    GET_LISTING_METRICS = "get_listing_metrics"
    GET_ORDERS = "get_orders"
    BULK_OPERATIONS = "bulk_operations"


class PlatformRegistry:
    """Platform adapter registry and resolver.

    Manages platform adapter registration, capability tracking,
    and runtime adapter resolution.
    """

    def __init__(self):
        self._adapters: dict[str, type[PlatformAdapter]] = {}
        self._capabilities: dict[str, set[str]] = {}
        self._adapter_cache: dict[str, PlatformAdapter] = {}
        self.logger = get_logger(__name__)

    def register_adapter(
        self,
        platform: TargetPlatform,
        adapter_class: type[PlatformAdapter],
        capabilities: set[str],
    ) -> None:
        """Register a platform adapter with its capabilities.

        Args:
            platform: Target platform enum
            adapter_class: Adapter class (not instance)
            capabilities: Set of supported capability strings
        """
        platform_key = platform.value
        self._adapters[platform_key] = adapter_class
        self._capabilities[platform_key] = capabilities
        self.logger.info(
            f"Registered adapter for {platform_key} with capabilities: {capabilities}"
        )

    def get_adapter(
        self,
        platform: TargetPlatform | str,
        region: str,
        mock: bool | None = None,
    ) -> PlatformAdapter:
        """Get adapter instance for platform/region.

        Args:
            platform: Target platform (enum or string)
            region: Region code (e.g., "us", "uk")
            mock: Force mock mode (None = use settings)

        Returns:
            PlatformAdapter instance

        Raises:
            ValueError: If platform not registered
        """
        platform_enum = platform if isinstance(platform, TargetPlatform) else TargetPlatform(platform)
        platform_key = platform_enum.value

        # Determine mock mode
        settings = get_settings()
        if mock is None:
            # Use settings for Temu, default False for others
            use_mock = platform_enum == TargetPlatform.TEMU and settings.temu_use_mock
        else:
            use_mock = mock

        # Build cache key
        cache_suffix = "mock" if use_mock else "live"
        cache_key = f"{platform_key}_{region}_{cache_suffix}"

        # Return cached instance if available
        if cache_key in self._adapter_cache:
            return self._adapter_cache[cache_key]

        # Check if platform registered
        if platform_key not in self._adapters:
            raise ValueError(f"Platform {platform_key} not registered")

        # Instantiate adapter
        adapter_class = self._adapters[platform_key]

        # Special handling for Temu (live vs mock)
        if platform_enum == TargetPlatform.TEMU:
            from app.services.platforms.temu import get_temu_adapter
            adapter = get_temu_adapter(region=region, mock=use_mock)
        else:
            # Generic instantiation (works for MockPlatformAdapter)
            adapter = adapter_class(platform_enum)

        # Cache and return
        self._adapter_cache[cache_key] = adapter
        return adapter

    def supports_feature(
        self,
        platform: TargetPlatform | str,
        feature: str,
    ) -> bool:
        """Check if platform supports a feature.

        Args:
            platform: Target platform (enum or string)
            feature: Feature name (use PlatformCapability constants)

        Returns:
            True if platform supports feature, False otherwise
        """
        platform_enum = platform if isinstance(platform, TargetPlatform) else TargetPlatform(platform)
        platform_key = platform_enum.value

        if platform_key not in self._capabilities:
            return False

        return feature in self._capabilities[platform_key]

    def get_supported_platforms(self) -> list[TargetPlatform]:
        """Get list of all registered platforms.

        Returns:
            List of TargetPlatform enums
        """
        return [TargetPlatform(key) for key in self._adapters.keys()]

    def get_platform_capabilities(self, platform: TargetPlatform | str) -> set[str]:
        """Get all capabilities for a platform.

        Args:
            platform: Target platform (enum or string)

        Returns:
            Set of capability strings
        """
        platform_enum = platform if isinstance(platform, TargetPlatform) else TargetPlatform(platform)
        platform_key = platform_enum.value
        return self._capabilities.get(platform_key, set())


# Global registry instance
_registry = PlatformRegistry()


def _initialize_registry() -> None:
    """Initialize global registry with platform adapters."""
    from app.services.platforms.base import MockPlatformAdapter
    from app.services.platforms.temu import TemuAdapter

    # Register Temu (full capabilities)
    _registry.register_adapter(
        TargetPlatform.TEMU,
        TemuAdapter,
        {
            PlatformCapability.CREATE_LISTING,
            PlatformCapability.UPDATE_LISTING,
            PlatformCapability.SYNC_INVENTORY,
            PlatformCapability.SYNC_PRICE,
        },
    )

    # Register mock adapters for other platforms (limited capabilities)
    for platform in [
        TargetPlatform.AMAZON,
        TargetPlatform.OZON,
        TargetPlatform.ALIEXPRESS,
        TargetPlatform.WILDBERRIES,
        TargetPlatform.SHOPEE,
        TargetPlatform.MERCADO_LIBRE,
        TargetPlatform.TIKTOK_SHOP,
        TargetPlatform.EBAY,
        TargetPlatform.WALMART,
        TargetPlatform.RAKUTEN,
        TargetPlatform.ALLEGRO,
    ]:
        _registry.register_adapter(
            platform,
            MockPlatformAdapter,
            {PlatformCapability.CREATE_LISTING},  # Mock only supports basic creation
        )


# Initialize on module load
_initialize_registry()


def get_platform_registry() -> PlatformRegistry:
    """Get global platform registry instance.

    Returns:
        Global PlatformRegistry instance
    """
    return _registry


__all__ = [
    "PlatformRegistry",
    "PlatformCapability",
    "get_platform_registry",
]
