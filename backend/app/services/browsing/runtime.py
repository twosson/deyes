"""Browser runtime that bridges browsing sessions to the existing browser pool."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from app.core.config import get_settings
from app.services.browser_pool import BrowserPool
from app.services.browsing.models import BrowsingSession


class BrowserRuntime:
    """Allocate pages for resolved browsing sessions."""

    def __init__(self, browser_pool: Optional[BrowserPool] = None):
        self.settings = get_settings()
        self._browser_pool = browser_pool

    async def get_pool(self) -> BrowserPool:
        """Get or create the shared browser pool."""
        if self._browser_pool is None:
            self._browser_pool = await BrowserPool.get_instance(
                max_browsers=self.settings.scraper_max_browsers,
                max_contexts_per_browser=self.settings.scraper_max_contexts_per_browser,
                browser_failure_threshold=self.settings.scraper_browser_failure_threshold,
                cleanup_interval_seconds=self.settings.scraper_browser_cleanup_interval_seconds,
            )
        return self._browser_pool

    @asynccontextmanager
    async def get_page(self, session: BrowsingSession):
        """Yield a page configured for the resolved browsing session."""
        pool = await self.get_pool()
        proxy = None
        if session.request.override_proxy_endpoint is not None:
            proxy = session.request.override_proxy_endpoint.server
        elif session.proxy_lease is not None:
            proxy = session.proxy_lease.endpoint.server

        async with pool.get_page(region=session.request.region, proxy=proxy) as page:
            yield page

    def get_stats(self) -> dict:
        """Return browser runtime stats from the underlying pool."""
        if self._browser_pool is None:
            return {
                "browser_count": 0,
                "max_browsers": self.settings.scraper_max_browsers,
                "max_contexts_per_browser": self.settings.scraper_max_contexts_per_browser,
                "active_context_count_total": 0,
            }
        return self._browser_pool.get_stats()
    async def close(self) -> None:
        """Close the underlying runtime resources."""
        if self._browser_pool is not None:
            await self._browser_pool.close()
            self._browser_pool = None
