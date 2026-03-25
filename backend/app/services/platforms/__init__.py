"""Platform adapter resolution helpers."""
from __future__ import annotations

from app.core.config import get_settings
from app.core.enums import TargetPlatform
from app.services.platforms.base import MockPlatformAdapter, PlatformAdapter
from app.services.platforms.temu import get_temu_adapter

_ADAPTER_CACHE: dict[str, PlatformAdapter] = {}


def get_platform_adapter(platform: TargetPlatform | str, region: str) -> PlatformAdapter:
    """Resolve and cache a platform adapter for the given platform/region pair."""
    platform_enum = platform if isinstance(platform, TargetPlatform) else TargetPlatform(platform)
    settings = get_settings()
    cache_suffix = "mock" if platform_enum == TargetPlatform.TEMU and settings.temu_use_mock else "live"
    cache_key = f"{platform_enum.value}_{region}_{cache_suffix}"

    if cache_key not in _ADAPTER_CACHE:
        if platform_enum == TargetPlatform.TEMU:
            _ADAPTER_CACHE[cache_key] = get_temu_adapter(
                region=region,
                mock=settings.temu_use_mock,
            )
        elif platform_enum == TargetPlatform.AMAZON:
            _ADAPTER_CACHE[cache_key] = MockPlatformAdapter(TargetPlatform.AMAZON)
        elif platform_enum == TargetPlatform.OZON:
            _ADAPTER_CACHE[cache_key] = MockPlatformAdapter(TargetPlatform.OZON)
        else:
            _ADAPTER_CACHE[cache_key] = MockPlatformAdapter(platform_enum)

    return _ADAPTER_CACHE[cache_key]


__all__ = ["get_platform_adapter", "PlatformAdapter"]
