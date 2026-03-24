"""High-level browsing service API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from app.services.browser_pool import BrowserPool
from app.services.browsing.models import BrowsingRequest
from app.services.browsing.providers import ProxyProvider
from app.services.browsing.runtime import BrowserRuntime
from app.services.browsing.session_coordinator import SessionCoordinator


class BrowsingService:
    """Coordinate session resolution, runtime allocation, and health reporting."""

    def __init__(
        self,
        *,
        runtime: BrowserRuntime | None = None,
        session_coordinator: SessionCoordinator | None = None,
        proxy_providers: list[ProxyProvider] | None = None,
        browser_pool: Optional[BrowserPool] = None,
    ):
        self._proxy_providers = list(proxy_providers or [])
        self._runtime = runtime or BrowserRuntime(browser_pool=browser_pool)
        self._session_coordinator = session_coordinator or SessionCoordinator(
            proxy_providers=self._proxy_providers
        )

    @asynccontextmanager
    async def get_page(self, request: BrowsingRequest):
        """Resolve a browsing request into a page allocation."""
        session = await self._session_coordinator.acquire_session(request)
        try:
            async with self._runtime.get_page(session) as page:
                yield page
            await self._session_coordinator.report_success(session)
        except Exception as exc:
            await self._session_coordinator.report_failure(session, error=str(exc))
            raise

    def get_stats(self) -> dict:
        """Return combined session and runtime stats."""
        provider_stats = [provider.get_stats() for provider in self._proxy_providers]
        return {
            "runtime": self._runtime.get_stats(),
            "sessions": self._session_coordinator.get_stats(),
            "providers": provider_stats,
        }

    async def close(self) -> None:
        """Close runtime resources."""
        await self._runtime.close()
