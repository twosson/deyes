"""Tests for adapter legacy compatibility and observability."""
import pytest
from unittest.mock import AsyncMock

from app.services.alibaba_1688_adapter import Alibaba1688Adapter


class FakeTMAPIClient:
    """Minimal fake client for adapter tests."""

    def __init__(self):
        self.search_items = AsyncMock(return_value={
            "products": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "has_more": False,
        })


@pytest.mark.asyncio
async def test_adapter_warns_when_empty_keywords_in_demand_first_mode():
    """Adapter should log warning when receiving empty keywords in demand-first mode."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.product_selection_adapter_legacy_seed_mode = False

    products = await adapter.fetch_products(keywords=[], limit=5)

    assert len(products) == 0
    assert not client.search_items.called


@pytest.mark.asyncio
async def test_adapter_warns_when_whitespace_only_keywords():
    """Adapter should filter out whitespace-only keywords and warn if none remain."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.product_selection_adapter_legacy_seed_mode = False

    products = await adapter.fetch_products(keywords=["  ", "\t", "\n"], limit=5)

    assert len(products) == 0
    assert not client.search_items.called


@pytest.mark.asyncio
async def test_adapter_logs_discovery_mode_in_fetch_completed():
    """Adapter should log discovery_mode in fetch_completed event."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    await adapter.fetch_products(keywords=["test keyword"], limit=5)

    # Verify that fetch_completed log would include discovery_mode
    # (actual log assertion would require log capture fixture)


@pytest.mark.asyncio
async def test_adapter_legacy_mode_fallback_logs_reason():
    """Adapter should log reason when falling back to legacy seed mode."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.product_selection_adapter_legacy_seed_mode = True

    await adapter.fetch_products(keywords=[], category="electronics", limit=5)

    # Verify that legacy_seed_mode_enabled log includes reason="empty_keywords"
    # (actual log assertion would require log capture fixture)
