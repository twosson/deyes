"""Tests for the browsing service layers."""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.services.browsing import (
    BrowsingRequest,
    BrowsingService,
    SessionCoordinator,
    StaticProxyProvider,
)


class FakePage:
    """Minimal fake Playwright page."""

    def __init__(self):
        self.url = "https://example.com"


class RecordingRuntime:
    """Test double for BrowserRuntime."""

    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.sessions = []
        self.closed = False

    @asynccontextmanager
    async def get_page(self, session):
        self.sessions.append(session)
        if self.error is not None:
            raise self.error
        yield FakePage()

    def get_stats(self) -> dict:
        return {"browser_count": 1, "active_context_count_total": 0}

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_static_proxy_provider_prefers_matching_region():
    """Static provider should prefer region-matching proxies when available."""
    provider = StaticProxyProvider([
        "http://global-proxy",
        "http://us-proxy#us",
        "http://de-proxy#de",
    ])

    lease = await provider.lease(region="us", session_token="abc")

    assert lease is not None
    assert lease.endpoint.server in {"http://global-proxy", "http://us-proxy"}
    assert lease.region in {None, "us"}


@pytest.mark.asyncio
async def test_session_coordinator_reuses_sticky_proxy_lease():
    """Sticky sessions should keep the same leased proxy identity."""
    provider = StaticProxyProvider(["http://us-proxy#us"])
    coordinator = SessionCoordinator(proxy_providers=[provider])
    request = BrowsingRequest(
        target="temu",
        region="us",
        network_mode="sticky",
        session_scope="workflow",
    )

    session_a = await coordinator.acquire_session(request)
    session_b = await coordinator.acquire_session(request)

    assert session_a.session_id == session_b.session_id
    assert session_a.proxy_lease is not None
    assert session_b.proxy_lease is not None
    assert session_a.proxy_lease.lease_id == session_b.proxy_lease.lease_id
    assert session_a.browser_family_key == session_b.browser_family_key


@pytest.mark.asyncio
async def test_browsing_service_reports_success_to_coordinator():
    """Successful page allocation should keep the session healthy."""
    provider = StaticProxyProvider(["http://proxy-us#us"])
    runtime = RecordingRuntime()
    service = BrowsingService(
        runtime=runtime,
        proxy_providers=[provider],
    )
    request = BrowsingRequest(
        target="temu",
        workflow="product_discovery",
        region="us",
        network_mode="sticky",
        session_scope="workflow",
    )

    async with service.get_page(request) as page:
        assert page.url == "https://example.com"

    stats = service.get_stats()
    assert len(runtime.sessions) == 1
    assert stats["sessions"]["session_count"] == 1
    assert stats["sessions"]["healthy_session_count"] == 1
    assert stats["providers"][0]["healthy_proxy_count"] == 1


@pytest.mark.asyncio
async def test_browsing_service_reports_failure_to_coordinator():
    """Runtime failures should increase session failure counts."""
    runtime = RecordingRuntime(error=RuntimeError("runtime failed"))
    service = BrowsingService(runtime=runtime)
    request = BrowsingRequest(target="temu", region="us")

    with pytest.raises(RuntimeError, match="runtime failed"):
        async with service.get_page(request):
            pass

    stats = service.get_stats()
    assert stats["sessions"]["session_count"] == 1
    assert stats["sessions"]["sessions"][0]["failure_count"] == 1


@pytest.mark.asyncio
async def test_browsing_service_close_closes_runtime():
    """Closing the browsing service should close the runtime."""
    runtime = RecordingRuntime()
    service = BrowsingService(runtime=runtime)

    await service.close()

    assert runtime.closed is True
