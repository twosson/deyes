"""Tests for seasonal seed expander service."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.seasonal_calendar import SeasonalEvent
from app.services.seasonal_seed_expander import SeasonalSeedExpander


class TestSeasonalSeedExpander:
    """Test SeasonalSeedExpander."""

    @pytest.fixture
    def mock_sglang_client(self):
        """Create mock SGLang client."""
        client = AsyncMock()
        client.generate_structured_json = AsyncMock()
        return client

    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client."""
        client = AsyncMock()
        client.get = AsyncMock(return_value=None)
        client.set = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def sample_event(self):
        """Create sample seasonal event."""
        return SeasonalEvent(
            name="Father's Day",
            date=date(2026, 6, 21),
            categories={"electronics": 1.4, "sports": 1.3},
            description="Gifts for fathers",
            region="US",
        )

    @pytest.mark.asyncio
    async def test_expand_success(self, mock_sglang_client, mock_redis_client, sample_event):
        """Test successful expansion."""
        mock_sglang_client.generate_structured_json.return_value = {
            "queries": [
                "wireless earbuds for dad",
                "desk gadget gift",
                "portable power bank",
                "phone stand gift",
            ]
        }

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        result = await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=5,
        )

        assert len(result) == 4
        assert "wireless earbuds for dad" in result
        assert "desk gadget gift" in result
        assert "portable power bank" in result
        assert "phone stand gift" in result

        # Verify LLM was called
        mock_sglang_client.generate_structured_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_expand_with_cache_hit(self, mock_sglang_client, mock_redis_client, sample_event):
        """Test expansion with cache hit."""
        cached_value = "wireless earbuds for dad||desk gadget gift||portable power bank"
        mock_redis_client.get.return_value = cached_value

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        result = await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=5,
        )

        assert len(result) == 3
        assert "wireless earbuds for dad" in result
        assert "desk gadget gift" in result

        # Verify LLM was NOT called
        mock_sglang_client.generate_structured_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_expand_empty_result(self, mock_sglang_client, mock_redis_client, sample_event):
        """Test expansion with empty LLM result."""
        mock_sglang_client.generate_structured_json.return_value = {"queries": []}

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        result = await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=5,
        )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_expand_llm_exception(self, mock_sglang_client, mock_redis_client, sample_event):
        """Test expansion with LLM exception."""
        mock_sglang_client.generate_structured_json.side_effect = Exception("LLM error")

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        result = await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=5,
        )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_expand_deduplication(self, mock_sglang_client, mock_redis_client, sample_event):
        """Test expansion deduplicates results."""
        mock_sglang_client.generate_structured_json.return_value = {
            "queries": [
                "wireless earbuds",
                "Wireless Earbuds",  # Duplicate with different case
                "  wireless earbuds  ",  # Duplicate with whitespace
                "desk gadget",
            ]
        }

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        result = await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=5,
        )

        assert len(result) == 2
        assert "wireless earbuds" in result
        assert "desk gadget" in result

    @pytest.mark.asyncio
    async def test_expand_filters_short_queries(
        self, mock_sglang_client, mock_redis_client, sample_event
    ):
        """Test expansion filters out very short queries."""
        mock_sglang_client.generate_structured_json.return_value = {
            "queries": [
                "abc",  # Too short (3 chars)
                "wireless earbuds",  # Valid
                "xy",  # Too short
                "desk gadget",  # Valid
            ]
        }

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        result = await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=5,
        )

        assert len(result) == 2
        assert "wireless earbuds" in result
        assert "desk gadget" in result

    @pytest.mark.asyncio
    async def test_expand_respects_limit(self, mock_sglang_client, mock_redis_client, sample_event):
        """Test expansion respects limit parameter."""
        mock_sglang_client.generate_structured_json.return_value = {
            "queries": [
                "query1",
                "query2",
                "query3",
                "query4",
                "query5",
            ]
        }

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        result = await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=3,
        )

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_expand_caches_result(self, mock_sglang_client, mock_redis_client, sample_event):
        """Test expansion caches successful result."""
        mock_sglang_client.generate_structured_json.return_value = {
            "queries": ["wireless earbuds", "desk gadget"]
        }

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=5,
        )

        # Verify cache was set
        mock_redis_client.set.assert_called_once()
        call_args = mock_redis_client.set.call_args
        assert "wireless earbuds||desk gadget" in call_args[0]

    @pytest.mark.asyncio
    @patch("app.services.seasonal_seed_expander.get_settings")
    async def test_expand_disabled_via_config(
        self, mock_get_settings, mock_sglang_client, mock_redis_client, sample_event
    ):
        """Test expansion disabled via config."""
        mock_settings = MagicMock()
        mock_settings.seed_enable_seasonal_llm_expansion = False
        mock_get_settings.return_value = mock_settings

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        result = await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=5,
        )

        assert len(result) == 0
        mock_sglang_client.generate_structured_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_expand_redis_failure_graceful(
        self, mock_sglang_client, mock_redis_client, sample_event
    ):
        """Test expansion handles Redis failures gracefully."""
        mock_redis_client.get.side_effect = Exception("Redis error")
        mock_redis_client.set.side_effect = Exception("Redis error")

        mock_sglang_client.generate_structured_json.return_value = {
            "queries": ["wireless earbuds", "desk gadget"]
        }

        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        # Should still work despite Redis failures
        result = await expander.expand(
            event=sample_event,
            category="electronics",
            region="US",
            limit=5,
        )

        assert len(result) == 2
        assert "wireless earbuds" in result

    @pytest.mark.asyncio
    async def test_build_cache_key(self, mock_sglang_client, mock_redis_client, sample_event):
        """Test cache key building."""
        expander = SeasonalSeedExpander(
            sglang_client=mock_sglang_client,
            redis_client=mock_redis_client,
        )

        cache_key = expander._build_cache_key(
            event=sample_event,
            category="electronics",
            region="US",
        )

        assert "seasonal_seed_expander" in cache_key
        assert "US" in cache_key
        assert "electronics" in cache_key
        assert "Father's Day" in cache_key
        assert "2026-06-21" in cache_key
