"""Tests for TMAPI 1688 API client."""
from __future__ import annotations

import pytest

from app.services.tmapi_1688_client import TMAPI1688Client


@pytest.fixture
def tmapi_client():
    """Create client with test credentials."""
    return TMAPI1688Client(
        api_token="test_token",
        base_url="https://api.tmapi.test.local",
        timeout=10,
        max_retries=1,
    )


@pytest.mark.asyncio
async def test_search_items_uses_tmapi_protocol(tmapi_client, monkeypatch):
    """Client should call TMAPI search endpoint with query token auth."""
    captured: dict[str, object] = {}

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 200,
                "msg": "success",
                "data": {
                    "page": 1,
                    "page_size": 20,
                    "has_next_page": False,
                    "items": [
                        {
                            "item_id": "123456",
                            "title": "iPhone手机壳",
                            "price": "5.50",
                        }
                    ],
                },
            }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params or {}
            return MockResponse()

    monkeypatch.setattr("app.services.tmapi_1688_client.httpx.AsyncClient", MockAsyncClient)

    result = await tmapi_client.search_items(keyword="手机壳", page=1, page_size=20, language="zh")

    assert captured["url"] == "https://api.tmapi.test.local/1688/global/search/items"
    assert captured["params"]["apiToken"] == "test_token"
    assert captured["params"]["keyword"] == "手机壳"
    assert captured["params"]["page"] == 1
    assert captured["params"]["page_size"] == 20
    assert captured["params"]["language"] == "zh"
    assert result["products"][0]["item_id"] == "123456"


@pytest.mark.asyncio
async def test_get_item_detail_returns_data_body(tmapi_client, monkeypatch):
    """Client should return the nested data mapping."""

    async def mock_request(endpoint, params):
        assert endpoint == "/1688/global/item_detail"
        assert params == {"item_id": "123456", "language": "en"}
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "item_id": 123456,
                "title": "iPhone 15 Pro 手机壳透明防摔",
                "price": "5.50",
                "main_imgs": ["https://example.com/1.jpg"],
            },
        }

    monkeypatch.setattr(tmapi_client, "_request", mock_request)

    detail = await tmapi_client.get_item_detail(item_id="123456")

    assert detail["item_id"] == 123456
    assert detail["title"] == "iPhone 15 Pro 手机壳透明防摔"


@pytest.mark.asyncio
async def test_search_items_normalizes_tmapi_search_response(tmapi_client, monkeypatch):
    """Client should normalize TMAPI search envelopes into stable fields."""

    async def mock_request(endpoint, params):
        assert endpoint == "/1688/global/search/items"
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "page": 1,
                "page_size": 40,
                "has_next_page": True,
                "total_count": 98,
                "items": [
                    {"item_id": "100", "title": "商品A", "price": "10"},
                    {"item_id": "200", "title": "商品B", "price": "20"},
                ],
            },
        }

    monkeypatch.setattr(tmapi_client, "_request", mock_request)

    result = await tmapi_client.search_items(keyword="测试")

    assert result["total"] == 98
    assert result["page"] == 1
    assert result["page_size"] == 40
    assert result["has_more"] is True
    assert len(result["products"]) == 2


@pytest.mark.asyncio
async def test_get_item_shipping_returns_normalized_mapping(tmapi_client, monkeypatch):
    """Client should return shipping mapping payload."""

    async def mock_request(endpoint, params):
        assert endpoint == "/1688/item/shipping"
        assert params == {"item_id": "123456", "province": "广东", "total_quantity": 1}
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "total_fee": 8.0,
                "shipping_to": "广东",
            },
        }

    monkeypatch.setattr(tmapi_client, "_request", mock_request)

    fee = await tmapi_client.get_item_shipping(item_id="123456", province="广东")

    assert fee["total_fee"] == 8.0


@pytest.mark.asyncio
async def test_get_shop_info_requires_identifier(tmapi_client):
    """Shop info should require either shop_url or member_id."""
    with pytest.raises(ValueError, match="Either shop_url or member_id is required"):
        await tmapi_client.get_shop_info()


@pytest.mark.asyncio
async def test_get_shop_items_normalizes_shop_envelope(tmapi_client, monkeypatch):
    """Client should normalize TMAPI shop items envelopes."""

    async def mock_request(endpoint, params):
        assert endpoint == "/1688/shop/items/v2"
        assert params["shop_url"] == "https://shop.example.com"
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "page": 1,
                "page_size": 20,
                "total_count": 42,
                "items": [
                    {"item_id": "400", "title": "工厂直供手机壳", "price": "8"},
                ],
            },
        }

    monkeypatch.setattr(tmapi_client, "_request", mock_request)

    result = await tmapi_client.get_shop_items(shop_url="https://shop.example.com")

    assert result["total"] == 42
    assert len(result["products"]) == 1
    assert result["products"][0]["item_id"] == "400"


@pytest.mark.asyncio
async def test_api_error_handling_uses_code_semantics(tmapi_client, monkeypatch):
    """Client should raise on TMAPI API errors."""

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 401,
                "msg": "Invalid api token",
            }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            return MockResponse()

    monkeypatch.setattr("app.services.tmapi_1688_client.httpx.AsyncClient", MockAsyncClient)

    with pytest.raises(RuntimeError, match="Invalid api token"):
        await tmapi_client.search_items(keyword="test")


@pytest.mark.asyncio
async def test_transport_retries_then_raises(tmapi_client, monkeypatch):
    """Client should retry transport failures before raising."""
    attempts = 0

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            nonlocal attempts
            attempts += 1
            raise ValueError("bad json")

    monkeypatch.setattr("app.services.tmapi_1688_client.httpx.AsyncClient", MockAsyncClient)

    with pytest.raises(ValueError, match="bad json"):
        await tmapi_client.search_items(keyword="test")

    assert attempts == 1
