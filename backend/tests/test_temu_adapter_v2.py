"""Tests for TemuSourceAdapterV2 browsing service integration."""
from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.services.browsing import BrowsingRequest
from app.services.temu_adapter_v2 import TemuSourceAdapterV2


class FakeLogger:
    """Collect structured log calls for assertions."""

    def __init__(self):
        self.warning_calls: list[tuple[str, dict]] = []
        self.info_calls: list[tuple[str, dict]] = []
        self.error_calls: list[tuple[str, dict]] = []

    def warning(self, event: str, **kwargs):
        self.warning_calls.append((event, kwargs))

    def info(self, event: str, **kwargs):
        self.info_calls.append((event, kwargs))

    def error(self, event: str, **kwargs):
        self.error_calls.append((event, kwargs))


class FakePage:
    """Minimal fake page for successful adapter flows."""

    def __init__(self):
        self.url = "https://www.temu.com/search_result.html"
        self.goto_calls: list[tuple[str, str, int]] = []

    async def goto(self, url: str, wait_until: str, timeout: int):
        self.goto_calls.append((url, wait_until, timeout))

    async def content(self) -> str:
        return "<html></html>"


class RecordingBrowsingService:
    """Test double for BrowsingService."""

    def __init__(self, *, page: FakePage | None = None, error: Exception | None = None, stats: dict | None = None):
        self.page = page or FakePage()
        self.error = error
        self.stats = stats or {
            "runtime": {"browser_count": 1, "active_context_count_total": 0},
            "sessions": {"session_count": 0},
            "providers": [],
        }
        self.calls = 0
        self.requests: list[BrowsingRequest] = []

    @asynccontextmanager
    async def get_page(self, request: BrowsingRequest):
        self.calls += 1
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        yield self.page

    def get_stats(self) -> dict:
        return self.stats


@pytest.mark.asyncio
async def test_fetch_products_passes_region_to_browsing_service(monkeypatch):
    """Adapter should forward region to browsing service via BrowsingRequest."""
    service = RecordingBrowsingService()
    adapter = TemuSourceAdapterV2(browsing_service=service)

    monkeypatch.setattr(adapter.settings, "environment", "production")
    monkeypatch.setattr(adapter, "_apply_human_delay", AsyncMock())
    monkeypatch.setattr(adapter, "_wait_for_search_results", AsyncMock())
    monkeypatch.setattr(adapter, "_collect_product_payloads", AsyncMock(return_value=[]))
    monkeypatch.setattr(adapter, "_parse_product_payloads", lambda **_: [])

    products = await adapter.fetch_products(region="us")

    assert products == []
    assert service.calls == 1
    assert service.requests[0].region == "us"
    assert service.requests[0].target == "temu"


@pytest.mark.asyncio
async def test_fetch_products_retries_when_service_raises(monkeypatch):
    """Adapter retry behavior should remain unchanged when browsing service fails."""
    service = RecordingBrowsingService(error=RuntimeError("service unavailable"))
    adapter = TemuSourceAdapterV2(browsing_service=service)
    sleep_calls: list[int] = []

    monkeypatch.setattr(adapter.settings, "scraper_max_retries", 3)

    async def fake_sleep(delay: int | float):
        sleep_calls.append(delay)

    monkeypatch.setattr("app.services.temu_adapter_v2.asyncio.sleep", fake_sleep)

    products = await adapter.fetch_products(region="us")

    assert products == []
    assert service.calls == 3
    assert sleep_calls == [1, 2]


@pytest.mark.asyncio
async def test_fetch_products_logs_browsing_stats_on_failure(monkeypatch):
    """Failure logs should include browsing service stats snapshot."""
    stats = {
        "runtime": {
            "browser_count": 1,
            "active_context_count_total": 1,
            "retiring_browser_count": 1,
        },
        "sessions": {"session_count": 1, "healthy_session_count": 0},
        "providers": [],
    }
    service = RecordingBrowsingService(error=RuntimeError("service unavailable"), stats=stats)
    adapter = TemuSourceAdapterV2(browsing_service=service)
    fake_logger = FakeLogger()

    monkeypatch.setattr(adapter.settings, "scraper_max_retries", 1)
    monkeypatch.setattr(adapter, "logger", fake_logger)

    products = await adapter.fetch_products(
        keywords=["magsafe"],
        price_min=Decimal("5"),
        price_max=Decimal("10"),
        region="us",
    )

    assert products == []
    attempt_logs = [
        payload
        for event, payload in fake_logger.warning_calls
        if event == "temu_fetch_attempt_failed"
    ]
    assert len(attempt_logs) == 1
    assert attempt_logs[0]["pool_stats"] == stats
    assert attempt_logs[0]["error"] == "service unavailable"
