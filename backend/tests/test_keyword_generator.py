"""Tests for keyword generation service."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.keyword_generator import KeywordGenerator, KeywordResult


class TestKeywordResult:
    """Test KeywordResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = KeywordResult(
            keyword="wireless earbuds",
            search_volume=5000,
            trend_score=75,
            competition_density="medium",
            related_keywords=["bluetooth earbuds", "true wireless earbuds"],
            category="electronics",
            region="US",
        )

        result_dict = result.to_dict()

        assert result_dict["keyword"] == "wireless earbuds"
        assert result_dict["search_volume"] == 5000
        assert result_dict["trend_score"] == 75
        assert result_dict["competition_density"] == "medium"
        assert result_dict["related_keywords"] == ["bluetooth earbuds", "true wireless earbuds"]
        assert result_dict["category"] == "electronics"
        assert result_dict["region"] == "US"


class TestKeywordGenerator:
    """Test KeywordGenerator service."""

    def test_init_default(self):
        """Test initialization with defaults."""
        generator = KeywordGenerator()

        assert generator.cache_ttl_seconds == 86400
        assert generator.enable_cache is True
        assert generator.min_trend_score == 20
        assert generator.redis_client is None

    def test_init_custom(self):
        """Test initialization with custom values."""
        mock_redis = MagicMock()
        generator = KeywordGenerator(
            redis_client=mock_redis,
            cache_ttl_seconds=3600,
            enable_cache=False,
            min_trend_score=30,
        )

        assert generator.redis_client == mock_redis
        assert generator.cache_ttl_seconds == 3600
        assert generator.enable_cache is False
        assert generator.min_trend_score == 30

    def test_region_to_geo(self):
        """Test region code conversion."""
        generator = KeywordGenerator()

        assert generator._region_to_geo("US") == "united_states"
        assert generator._region_to_geo("UK") == "united_kingdom"
        assert generator._region_to_geo("GB") == "united_kingdom"
        assert generator._region_to_geo("JP") == "japan"
        assert generator._region_to_geo("UNKNOWN") == "united_states"

    def test_estimate_search_volume_from_interest(self):
        """Test search volume estimation from interest."""
        generator = KeywordGenerator()

        assert generator._estimate_search_volume_from_interest(80) == 10000
        assert generator._estimate_search_volume_from_interest(60) == 5000
        assert generator._estimate_search_volume_from_interest(40) == 2000
        assert generator._estimate_search_volume_from_interest(20) == 500
        assert generator._estimate_search_volume_from_interest(10) == 200
        assert generator._estimate_search_volume_from_interest(5) == 100

    def test_heuristic_competition_assessment_generic(self):
        """Test heuristic competition for generic keywords."""
        generator = KeywordGenerator()

        assert generator._heuristic_competition_assessment("phone") == "high"
        assert generator._heuristic_competition_assessment("laptop") == "high"

    def test_heuristic_competition_assessment_specific(self):
        """Test heuristic competition for specific keywords."""
        generator = KeywordGenerator()

        assert generator._heuristic_competition_assessment("wireless phone charger") == "medium"
        assert generator._heuristic_competition_assessment("blue running shoes men") == "medium"

    def test_heuristic_competition_assessment_long_tail(self):
        """Test heuristic competition for long-tail keywords."""
        generator = KeywordGenerator()

        assert (
            generator._heuristic_competition_assessment(
                "waterproof wireless phone charger for car"
            )
            == "low"
        )
        assert (
            generator._heuristic_competition_assessment("blue running shoes for men size 10")
            == "low"
        )

    def test_heuristic_competition_assessment_brand(self):
        """Test heuristic competition for brand names."""
        generator = KeywordGenerator()

        assert generator._heuristic_competition_assessment("iphone case") == "high"
        assert generator._heuristic_competition_assessment("nike shoes") == "high"
        assert generator._heuristic_competition_assessment("samsung galaxy phone") == "high"

    def test_is_category_relevant_electronics(self):
        """Test category relevance for electronics."""
        generator = KeywordGenerator()

        assert generator._is_category_relevant("wireless headphones", "electronics") is True
        assert generator._is_category_relevant("bluetooth speaker", "electronics") is True
        assert generator._is_category_relevant("summer dress", "electronics") is True  # Default: accept all

    def test_is_category_relevant_fashion(self):
        """Test category relevance for fashion."""
        generator = KeywordGenerator()

        assert generator._is_category_relevant("summer dress", "fashion") is True
        assert generator._is_category_relevant("running shoes", "fashion") is True
        assert generator._is_category_relevant("leather bag", "fashion") is True

    def test_fallback_keywords_electronics(self):
        """Test fallback keywords for electronics."""
        generator = KeywordGenerator()

        results = generator._fallback_keywords("electronics", "US", 5)

        assert len(results) == 5
        assert all(isinstance(r, KeywordResult) for r in results)
        assert results[0].keyword == "wireless earbuds"
        assert results[0].category == "electronics"
        assert results[0].region == "US"

    def test_fallback_keywords_fashion(self):
        """Test fallback keywords for fashion."""
        generator = KeywordGenerator()

        results = generator._fallback_keywords("fashion", "US", 3)

        assert len(results) == 3
        assert results[0].keyword == "summer dress"
        assert results[0].category == "fashion"

    def test_fallback_keywords_unknown_category(self):
        """Test fallback keywords for unknown category."""
        generator = KeywordGenerator()

        results = generator._fallback_keywords("unknown", "US", 5)

        # Should default to electronics
        assert len(results) == 5
        assert results[0].keyword == "wireless earbuds"

    @pytest.mark.asyncio
    async def test_generate_trending_keywords_with_mock(self):
        """Test generate_trending_keywords with mocked pytrends."""
        generator = KeywordGenerator(min_trend_score=20)

        # Mock the _generate_from_pytrends method
        mock_results = [
            KeywordResult(
                keyword="wireless earbuds",
                search_volume=5000,
                trend_score=75,
                competition_density="medium",
                related_keywords=["bluetooth earbuds"],
                category="electronics",
                region="US",
            ),
            KeywordResult(
                keyword="phone case",
                search_volume=8000,
                trend_score=80,
                competition_density="high",
                related_keywords=["iphone case"],
                category="electronics",
                region="US",
            ),
        ]

        with patch.object(
            generator,
            "_generate_from_pytrends",
            return_value=mock_results,
        ):
            results = await generator.generate_trending_keywords(
                category="electronics",
                region="US",
                limit=10,
            )

        assert len(results) == 2
        assert results[0].keyword == "wireless earbuds"
        assert results[1].keyword == "phone case"

    @pytest.mark.asyncio
    async def test_expand_keyword_with_mock(self):
        """Test expand_keyword with mocked pytrends."""
        generator = KeywordGenerator()

        # Mock the _get_related_keywords method
        mock_related = ["bluetooth earbuds", "true wireless earbuds", "wireless headphones"]

        with patch.object(
            generator,
            "_get_related_keywords",
            return_value=mock_related,
        ):
            results = await generator.expand_keyword(
                keyword="wireless earbuds",
                region="US",
                limit=20,
            )

        assert len(results) == 3
        assert "bluetooth earbuds" in results
        assert "true wireless earbuds" in results

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cache hit scenario."""
        # Create mock Redis client
        mock_redis = AsyncMock()
        cached_results = [
            {
                "keyword": "wireless earbuds",
                "search_volume": 5000,
                "trend_score": 75,
                "competition_density": "medium",
                "related_keywords": ["bluetooth earbuds"],
                "category": "electronics",
                "region": "US",
            }
        ]
        import json

        mock_redis.get.return_value = json.dumps(cached_results)

        generator = KeywordGenerator(
            redis_client=mock_redis,
            enable_cache=True,
        )

        results = await generator.generate_trending_keywords(
            category="electronics",
            region="US",
            limit=10,
        )

        # Should get cached result
        assert len(results) == 1
        assert results[0].keyword == "wireless earbuds"
        assert results[0].search_volume == 5000

        # Should have called Redis get
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_and_save(self):
        """Test cache miss and save scenario."""
        # Create mock Redis client
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss
        mock_redis.set.return_value = True

        generator = KeywordGenerator(
            redis_client=mock_redis,
            enable_cache=True,
        )

        # Mock the _generate_from_pytrends method
        mock_results = [
            KeywordResult(
                keyword="wireless earbuds",
                search_volume=5000,
                trend_score=75,
                competition_density="medium",
                related_keywords=[],
                category="electronics",
                region="US",
            )
        ]

        with patch.object(
            generator,
            "_generate_from_pytrends",
            return_value=mock_results,
        ):
            results = await generator.generate_trending_keywords(
                category="electronics",
                region="US",
                limit=10,
            )

        # Should get fresh result
        assert len(results) == 1
        assert results[0].keyword == "wireless earbuds"

        # Should have called Redis get (cache miss)
        mock_redis.get.assert_called_once()

        # Should have called Redis set (save to cache)
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 86400  # Default TTL

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """Test with caching disabled."""
        generator = KeywordGenerator(
            enable_cache=False,
        )

        # Mock the _generate_from_pytrends method
        mock_results = [
            KeywordResult(
                keyword="wireless earbuds",
                search_volume=5000,
                trend_score=75,
                competition_density="medium",
                related_keywords=[],
                category="electronics",
                region="US",
            )
        ]

        with patch.object(
            generator,
            "_generate_from_pytrends",
            return_value=mock_results,
        ):
            results = await generator.generate_trending_keywords(
                category="electronics",
                region="US",
                limit=10,
            )

        # Should get result
        assert len(results) == 1
        assert results[0].keyword == "wireless earbuds"

        # Should NOT have created Redis client
        assert generator.redis_client is None


@pytest.mark.integration
class TestKeywordGeneratorIntegration:
    """Integration tests for KeywordGenerator with real pytrends.

    These tests require internet connection and may be rate-limited by Google.
    Run with: pytest -m integration
    """

    @pytest.mark.asyncio
    async def test_pytrends_real_trending_searches(self):
        """Test with real pytrends API call."""
        generator = KeywordGenerator(min_trend_score=10)

        # Use a popular category
        results = await generator.generate_trending_keywords(
            category="electronics",
            region="US",
            limit=10,
        )

        # Should have some results
        assert len(results) > 0

        # Should have valid data
        for result in results:
            assert result.keyword
            assert result.search_volume > 0
            assert result.trend_score >= 10
            assert result.competition_density in ["low", "medium", "high"]

    @pytest.mark.asyncio
    async def test_pytrends_expand_keyword(self):
        """Test keyword expansion with real pytrends."""
        generator = KeywordGenerator()

        # Use a popular keyword
        related = await generator.expand_keyword(
            keyword="iphone",
            region="US",
            limit=20,
        )

        # Should have some related keywords
        assert len(related) > 0
