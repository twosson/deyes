"""Tests for browser pool concurrency, cleanup, health, and stats."""
import asyncio
import time

import pytest

from app.services.browser_pool import BrowserInstance, BrowserPool


class FakePage:
    """Minimal fake Playwright page."""

    def __init__(self):
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class FakeContext:
    """Minimal fake Playwright context."""

    def __init__(self, *, new_page_error: Exception | None = None):
        self.new_page_error = new_page_error
        self.close_calls = 0
        self.init_scripts: list[str] = []

    async def add_init_script(self, script: str):
        self.init_scripts.append(script)

    async def new_page(self):
        if self.new_page_error is not None:
            raise self.new_page_error
        return FakePage()

    async def close(self):
        self.close_calls += 1


class FakeBrowser:
    """Minimal fake Playwright browser."""

    def __init__(self, *, context_factory=None, new_context_error: Exception | None = None):
        self.context_factory = context_factory or (lambda **_: FakeContext())
        self.new_context_error = new_context_error
        self.close_calls = 0
        self.context_kwargs: list[dict] = []

    async def new_context(self, **kwargs):
        self.context_kwargs.append(kwargs)
        if self.new_context_error is not None:
            raise self.new_context_error
        return self.context_factory(**kwargs)

    async def close(self):
        self.close_calls += 1


class FakePlaywright:
    """Minimal fake Playwright controller."""

    def __init__(self):
        self.stop_calls = 0

    async def stop(self):
        self.stop_calls += 1


@pytest.mark.asyncio
async def test_get_page_reserves_browser_slots_atomically(monkeypatch):
    """Concurrent requests should not over-allocate a single browser."""
    pool = BrowserPool(
        max_browsers=2,
        max_contexts_per_browser=1,
        cleanup_interval_seconds=3600,
    )
    created_instances: list[BrowserInstance] = []

    async def fake_create_browser():
        instance = BrowserInstance(browser=FakeBrowser(), playwright=FakePlaywright())
        created_instances.append(instance)
        return instance

    monkeypatch.setattr(pool, "_create_browser", fake_create_browser)

    release_event = asyncio.Event()
    both_entered = asyncio.Event()

    async def worker():
        async with pool.get_page():
            if pool.get_stats()["active_context_count_total"] == 2:
                both_entered.set()
            await release_event.wait()

    tasks = [asyncio.create_task(worker()) for _ in range(2)]

    await asyncio.wait_for(both_entered.wait(), timeout=1)
    stats = pool.get_stats()

    assert stats["browser_count"] == 2
    assert stats["active_context_count_total"] == 2
    assert [browser["active_context_count"] for browser in stats["browsers"]] == [1, 1]
    assert len(created_instances) == 2

    release_event.set()
    await asyncio.gather(*tasks)

    assert pool.get_stats()["active_context_count_total"] == 0


@pytest.mark.asyncio
async def test_cleanup_marks_active_old_browser_retiring_without_closing():
    """Cleanup should retire active browsers before closing them."""
    pool = BrowserPool(
        max_browsers=1,
        max_contexts_per_browser=2,
        browser_max_age_seconds=10,
        idle_timeout_seconds=5,
        cleanup_interval_seconds=3600,
    )
    instance = BrowserInstance(browser=FakeBrowser(), playwright=FakePlaywright())
    instance.created_at = time.time() - 20
    instance.active_context_count = 1
    pool.browsers.append(instance)

    await pool._cleanup_old_browsers()

    assert instance.retiring is True
    assert instance in pool.browsers
    assert instance.browser.close_calls == 0
    assert instance.playwright.stop_calls == 0


@pytest.mark.asyncio
async def test_retiring_browser_closes_after_last_slot_released():
    """A drained retiring browser should close exactly once."""
    pool = BrowserPool(max_browsers=1, max_contexts_per_browser=2, cleanup_interval_seconds=3600)
    instance = BrowserInstance(browser=FakeBrowser(), playwright=FakePlaywright())
    instance.retiring = True
    instance.active_context_count = 1
    pool.browsers.append(instance)

    await pool._release_browser_slot(instance)

    assert instance.active_context_count == 0
    assert instance not in pool.browsers
    assert instance.browser.close_calls == 1
    assert instance.playwright.stop_calls == 1


@pytest.mark.asyncio
async def test_new_page_failure_marks_browser_unhealthy_and_removes_it():
    """Browser instance failures should retire the instance and remove it from scheduling."""
    pool = BrowserPool(
        max_browsers=1,
        max_contexts_per_browser=1,
        browser_failure_threshold=1,
        cleanup_interval_seconds=3600,
    )
    page_error = RuntimeError("new page failed")
    instance = BrowserInstance(
        browser=FakeBrowser(context_factory=lambda **_: FakeContext(new_page_error=page_error)),
        playwright=FakePlaywright(),
    )
    pool.browsers.append(instance)

    with pytest.raises(RuntimeError, match="new page failed"):
        async with pool.get_page():
            pass

    assert instance.is_healthy is False
    assert instance.retiring is True
    assert instance.failure_count == 1
    assert instance.last_error_at is not None
    assert instance not in pool.browsers
    assert instance.browser.close_calls == 1
    assert instance.playwright.stop_calls == 1


def test_get_stats_reports_mixed_browser_health_and_proxy_counts():
    """Stats should include aggregate and per-browser runtime state."""
    pool = BrowserPool(max_browsers=4, max_contexts_per_browser=3, cleanup_interval_seconds=3600)

    healthy_instance = BrowserInstance(browser=FakeBrowser(), playwright=FakePlaywright())
    healthy_instance.active_context_count = 2
    healthy_instance.request_count = 5
    healthy_instance.created_at = time.time() - 15

    retiring_instance = BrowserInstance(browser=FakeBrowser(), playwright=FakePlaywright())
    retiring_instance.active_context_count = 1
    retiring_instance.request_count = 7
    retiring_instance.retiring = True

    unhealthy_instance = BrowserInstance(browser=FakeBrowser(), playwright=FakePlaywright())
    unhealthy_instance.is_healthy = False
    unhealthy_instance.retiring = True
    unhealthy_instance.failure_count = 3
    unhealthy_instance.last_error_at = time.time() - 1

    pool.browsers.extend([healthy_instance, retiring_instance, unhealthy_instance])
    pool.add_proxies(["http://proxy-1", "http://proxy-2"])
    pool.proxy_manager.proxies[1].is_healthy = False

    stats = pool.get_stats()

    assert stats["browser_count"] == 3
    assert stats["active_context_count_total"] == 3
    assert stats["healthy_browser_count"] == 1
    assert stats["retiring_browser_count"] == 2
    assert stats["unhealthy_browser_count"] == 1
    assert stats["proxy_count"] == 2
    assert stats["healthy_proxy_count"] == 1
    assert stats["unhealthy_proxy_count"] == 1
    assert stats["browsers"][0]["active_context_count"] == 2
    assert stats["browsers"][0]["request_count"] == 5
    assert stats["browsers"][1]["retiring"] is True
    assert stats["browsers"][2]["is_healthy"] is False
    assert stats["browsers"][2]["failure_count"] == 3
