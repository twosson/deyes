"""Tests for Helium 10 API client."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.clients.helium10 import Helium10Client


class TestHelium10Client:
    """Test Helium10Client."""

    def test_init_default(self):
        """Test initialization with defaults."""
        client = Helium10Client(api_key="test_key")

        assert client.api_key == "test_key"
        assert client.cache_ttl_seconds == 86400
        assert client.enable_cache is True

    def test_init_custom(self):
        """Test initialization with custom values."""
        client = Helium10Client(
            api_key="test_key",
            cache_ttl_seconds=3600,
            enable_cache=False,
        )

        assert client.api_key == "test_key"
        assert client.cache_ttl_seconds == 3600
        assert client.enable_cache is False

    @pytest.mark.asyncio
    async def test_get_keyword_data_success(self):
        """Test successful keyword data retrieval."""
        client = Helium10Client(api_key="test_key", enable_cache=False)

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "search_volume": 3000,
            "competition_score": 45,
            "trend_direction": "rising",
            "trend_growth_rate": 0.30,
        }

        with patch.object(client, "_get_http_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.get_keyword_data(
                keyword="phone case",
                marketplace="US",
            )

        assert result is not None
        assert result["search_volume"] == 3000
        assert result["competition_score"] == 45
        assert result["trend_direction"] == "rising"
        assert result["trend_growth_rate"] == 0.30

        # Verify API call
        mock_http_client.post.assert_called_once_with(
            "/magnet/keyword-data",
            json={
                "keyword": "phone case",
                "marketplace": "US",
            },
        )

    @pytest.mark.asyncio
    async def test_get_keyword_data_unauthorized(self):
        """Test handling of 401 unauthorized error."""
        client = Helium10Client(api_key="invalid_key", enable_cache=False)

        # Mock HTTP client to return 401
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.object(client, "_get_http_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.get_keyword_data(
                keyword="phone case",
                marketplace="US",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_keyword_data_rate_limited(self):
        """Test handling of 429 rate limit error."""
        client = Helium10Client(api_key="test_key", enable_cache=False)

        # Mock HTTP client to return 429
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch.object(client, "_get_http_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.get_keyword_data(
                keyword="phone case",
                marketplace="US",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_keyword_data_api_error(self):
        """Test handling of API error (non-200 status)."""
        client = Helium10Client(api_key="test_key", enable_cache=False)

        # Mock HTTP client to return 500
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(client, "_get_http_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.get_keyword_data(
                keyword="phone case",
                marketplace="US",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_keyword_data_timeout(self):
        """Test handling of timeout error."""
        client = Helium10Client(api_key="test_key", enable_cache=False)

        with patch.object(client, "_get_http_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.side_effect = httpx.TimeoutException("Timeout")
            mock_get_client.return_value = mock_http_client

            result = await client.get_keyword_data(
                keyword="phone case",
                marketplace="US",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_keyword_data_request_error(self):
        """Test handling of request error."""
        client = Helium10Client(api_key="test_key", enable_cache=False)

        with patch.object(client, "_get_http_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.side_effect = httpx.RequestError("Connection error")
            mock_get_client.return_value = mock_http_client

            result = await client.get_keyword_data(
                keyword="phone case",
                marketplace="US",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_keyword_data_unexpected_error(self):
        """Test handling of unexpected error."""
        client = Helium10Client(api_key="test_key", enable_cache=False)

        with patch.object(client, "_get_http_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.side_effect = Exception("Unexpected error")
            mock_get_client.return_value = mock_http_client

            result = await client.get_keyword_data(
                keyword="phone case",
                marketplace="US",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cache hit scenario."""
        # Create mock Redis client
        mock_redis = AsyncMock()
        cached_data = {
            "search_volume": 3000,
            "competition_score": 45,
            "trend_direction": "rising",
            "trend_growth_rate": 0.30,
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        client = Helium10Client(
            api_key="test_key",
            redis_client=mock_redis,
            enable_cache=True,
        )

        result = await client.get_keyword_data(
            keyword="phone case",
            marketplace="US",
        )

        # Should get cached result
        assert result is not None
        assert result["search_volume"] == 3000
        assert result["competition_score"] == 45

        # Should have called Redis get
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_and_save(self):
        """Test cache miss and save scenario."""
        # Create mock Redis client
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss
        mock_redis.set.return_value = True

        client = Helium10Client(
            api_key="test_key",
            redis_client=mock_redis,
            enable_cache=True,
        )

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "search_volume": 3000,
            "competition_score": 45,
            "trend_direction": "rising",
            "trend_growth_rate": 0.30,
        }

        with patch.object(client, "_get_http_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.get_keyword_data(
                keyword="phone case",
                marketplace="US",
            )

        # Should get fresh result
        assert result is not None
        assert result["search_volume"] == 3000

        # Should have called Redis get (cache miss)
        mock_redis.get.assert_called_once()

        # Should have called Redis set (save to cache)
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 86400  # Default TTL

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """Test with caching disabled."""
        client = Helium10Client(
            api_key="test_key",
            enable_cache=False,
        )

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "search_volume": 3000,
            "competition_score": 45,
            "trend_direction": "rising",
            "trend_growth_rate": 0.30,
        }

        with patch.object(client, "_get_http_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.get_keyword_data(
                keyword="phone case",
                marketplace="US",
            )

        # Should get result
        assert result is not None
        assert result["search_volume"] == 3000

        # Should NOT have created Redis client
        assert client.redis_client is None

    def test_build_cache_key(self):
        """Test cache key building."""
        client = Helium10Client(api_key="test_key")

        key1 = client._build_cache_key("phone case", "US")
        key2 = client._build_cache_key("phone case", "UK")
        key3 = client._build_cache_key("wireless charger", "US")

        # Same keyword + marketplace should produce same key
        assert key1 == client._build_cache_key("phone case", "US")

        # Different marketplace should produce different key
        assert key1 != key2

        # Different keyword should produce different key
        assert key1 != key3

        # Key should have expected format
        assert key1.startswith("helium10:")
        assert ":US" in key1

    @pytest.mark.asyncio
    async def test_close_http_client(self):
        """Test closing HTTP client."""
        client = Helium10Client(api_key="test_key")

        # Create HTTP client
        await client._get_http_client()
        assert client._http_client is not None

        # Close client
        await client.close()
        assert client._http_client is None

    @pytest.mark.asyncio
    async def test_http_client_headers(self):
        """Test HTTP client has correct headers."""
        client = Helium10Client(api_key="test_api_key_123")

        http_client = await client._get_http_client()

        assert http_client.headers["Authorization"] == "Bearer test_api_key_123"
        assert http_client.headers["Content-Type"] == "application/json"
        assert http_client.base_url == "https://api.helium10.com/v1"
        assert http_client.timeout.read == 30
