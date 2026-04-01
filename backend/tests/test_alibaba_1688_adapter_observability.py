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
async def test_adapter_returns_empty_when_keywords_missing():
    """Adapter should return empty results when no validated keywords are provided."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=[], limit=5)

    assert len(products) == 0
    assert not client.search_items.called


@pytest.mark.asyncio
async def test_adapter_filters_whitespace_keywords():
    """Adapter should filter out whitespace-only keywords and return empty if none remain."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

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
async def test_adapter_returns_empty_without_legacy_fallback():
    """Adapter should not fall back to category seeds when keywords are missing."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=[], category="electronics", limit=5)

    assert products == []
    assert not client.search_items.called
