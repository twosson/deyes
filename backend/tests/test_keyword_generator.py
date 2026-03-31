"""Tests for keyword generation service."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        mock_client = AsyncMock()
        generator = KeywordGenerator(
            redis_client=mock_redis,
            cache_ttl_seconds=3600,
            enable_cache=False,
            min_trend_score=30,
            alphashop_client=mock_client,
            platform="amazon",
            listing_time="90",
        )

        assert generator.redis_client == mock_redis
        assert generator.cache_ttl_seconds == 3600
        assert generator.enable_cache is False
        assert generator.min_trend_score == 30
        assert generator._alphashop_client == mock_client
        assert generator.platform == "amazon"
        assert generator.listing_time == "90"

    def test_region_to_geo(self):
        """Test legacy region code conversion helper."""
        generator = KeywordGenerator()

        assert generator._region_to_geo("US") == "united_states"
        assert generator._region_to_geo("UK") == "united_kingdom"
        assert generator._region_to_geo("GB") == "united_kingdom"
        assert generator._region_to_geo("JP") == "japan"
        assert generator._region_to_geo("UNKNOWN") == "united_states"

    def test_estimate_search_volume_from_interest(self):
        """Test search volume estimation helper."""
        generator = KeywordGenerator()

        assert generator._estimate_search_volume_from_interest(80) == 10000
        assert generator._estimate_search_volume_from_interest(60) == 5000
        assert generator._estimate_search_volume_from_interest(40) == 2000
        assert generator._estimate_search_volume_from_interest(20) == 500
        assert generator._estimate_search_volume_from_interest(10) == 200
        assert generator._estimate_search_volume_from_interest(5) == 100

    def test_extract_search_volume_from_alphashop(self):
        """Test AlphaShop search volume mapping."""
        generator = KeywordGenerator()

        assert generator._extract_search_volume_from_alphashop({"searchVolume": 3000}) == 3000
        assert generator._extract_search_volume_from_alphashop({"salesInfo": {"searchVolume": 2500}}) == 2500
        assert generator._extract_search_volume_from_alphashop({"soldCnt30d": 400}) == 4000
        assert generator._extract_search_volume_from_alphashop({"searchRank": 800}) == 10000
        assert generator._extract_search_volume_from_alphashop({"searchRank": 7000}) == 2000
        assert generator._extract_search_volume_from_alphashop({"oppScore": 60}) == 5000

    def test_extract_trend_score_from_alphashop(self):
        """Test AlphaShop trend score mapping."""
        generator = KeywordGenerator(min_trend_score=20)

        assert generator._extract_trend_score_from_alphashop({"oppScore": 85}) == 85
        assert generator._extract_trend_score_from_alphashop({"searchRank": 50}) == 90
        assert generator._extract_trend_score_from_alphashop({"searchRank": 1500}) == 60
        assert generator._extract_trend_score_from_alphashop({}) == 20

    def test_extract_competition_density_from_alphashop(self):
        """Test AlphaShop competition density mapping."""
        generator = KeywordGenerator()

        assert generator._extract_competition_density_from_alphashop({"searchRank": 500}, "phone case") == "high"
        assert generator._extract_competition_density_from_alphashop({"searchRank": 5000}, "phone case") == "medium"
        assert generator._extract_competition_density_from_alphashop({"searchRank": 20000}, "phone case") == "low"
        assert generator._extract_competition_density_from_alphashop({"oppScore": 85}, "phone case") == "high"
        assert generator._extract_competition_density_from_alphashop({"oppScore": 65}, "phone case") == "medium"
        assert generator._extract_competition_density_from_alphashop({"oppScore": 30}, "phone case") == "low"

    def test_extract_keyword_text(self):
        """Test keyword text extraction from AlphaShop variants."""
        generator = KeywordGenerator()

        assert generator._extract_keyword_text({"keyword": "phone case"}) == "phone case"
        assert generator._extract_keyword_text({"query": "laptop stand"}) == "laptop stand"
        assert generator._extract_keyword_text({"title": "usb cable"}) == "usb cable"
        assert generator._extract_keyword_text({"radar": {"keyword": "wireless earbuds"}}) == "wireless earbuds"
        assert generator._extract_keyword_text({"unknown": "value"}) is None

    def test_extract_related_keywords_from_item(self):
        """Test related keyword extraction."""
        generator = KeywordGenerator()

        item = {
            "relatedKeywords": ["bluetooth earbuds", "true wireless earbuds"],
            "keywordList": [{"keyword": "noise cancelling earbuds"}],
            "radar": {
                "propertyList": [
                    {"value": "sports earbuds"},
                    {"name": "gaming earbuds"},
                ]
            },
        }

        result = generator._extract_related_keywords_from_item(item, "wireless earbuds")

        assert "bluetooth earbuds" in result
        assert "true wireless earbuds" in result
        assert "noise cancelling earbuds" in result
        assert "sports earbuds" in result
        assert "gaming earbuds" in result
        assert "wireless earbuds" not in result

    def test_extract_rank_trends(self):
        """Test rank trend extraction."""
        generator = KeywordGenerator()

        item = {
            "rankTrends": [100, "200", {"rank": 300}, {"value": 400}, {"searchRank": 500}, "bad"]
        }

        result = generator._extract_rank_trends(item)

        assert result == [100, 200, 300, 400, 500]

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
        assert generator._is_category_relevant("summer dress", "electronics") is True

    def test_is_category_relevant_fashion(self):
        """Test category relevance for fashion."""
        generator = KeywordGenerator()

        assert generator._is_category_relevant("summer dress", "fashion") is True
        assert generator._is_category_relevant("running shoes", "fashion") is True
        assert generator._is_category_relevant("leather bag", "fashion") is True

    @pytest.mark.asyncio
    async def test_generate_trending_keywords_with_alphashop(self):
        """Test generate_trending_keywords with AlphaShop data."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "wireless earbuds",
                    "searchVolume": 5000,
                    "oppScore": 75,
                    "searchRank": 3000,
                    "relatedKeywords": ["bluetooth earbuds"],
                },
                {
                    "keyword": "phone case",
                    "searchVolume": 8000,
                    "oppScore": 80,
                    "searchRank": 500,
                    "relatedKeywords": ["iphone case"],
                },
            ]
        }

        generator = KeywordGenerator(min_trend_score=20, alphashop_client=mock_client)

        results = await generator.generate_trending_keywords(
            category="electronics",
            region="US",
            limit=10,
        )

        assert len(results) == 2
        # Sorted by trend_score descending
        assert results[0].keyword == "phone case"
        assert results[1].keyword == "wireless earbuds"
        assert results[0].competition_density == "high"
        assert results[1].competition_density == "medium"

    @pytest.mark.asyncio
    async def test_generate_trending_keywords_filters_low_trend_scores(self):
        """Test low AlphaShop trend scores are filtered out."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {"keyword": "usb cable", "oppScore": 10, "searchVolume": 3000},
                {"keyword": "wireless earbuds", "oppScore": 70, "searchVolume": 5000},
            ]
        }

        generator = KeywordGenerator(min_trend_score=20, alphashop_client=mock_client)

        results = await generator.generate_trending_keywords(
            category="electronics",
            region="US",
            limit=10,
        )

        assert len(results) == 1
        assert results[0].keyword == "wireless earbuds"

    @pytest.mark.asyncio
    async def test_generate_trending_keywords_raises_when_alphashop_empty(self):
        """Test RuntimeError is raised when AlphaShop returns no data."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {"keyword_list": []}

        generator = KeywordGenerator(alphashop_client=mock_client)

        with pytest.raises(RuntimeError, match="Keyword generation failed"):
            await generator.generate_trending_keywords(
                category="electronics",
                region="US",
                limit=3,
            )

    @pytest.mark.asyncio
    async def test_generate_trending_keywords_raises_on_error(self):
        """Test RuntimeError is raised when AlphaShop raises error."""
        mock_client = AsyncMock()
        mock_client.search_keywords.side_effect = Exception("API error")

        generator = KeywordGenerator(alphashop_client=mock_client)

        with pytest.raises(RuntimeError, match="Keyword generation failed"):
            await generator.generate_trending_keywords(
                category="electronics",
                region="US",
                limit=3,
            )

    @pytest.mark.asyncio
    async def test_expand_keyword_with_alphashop(self):
        """Test expand_keyword with AlphaShop search."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {"keyword": "bluetooth earbuds"},
                {"keyword": "true wireless earbuds"},
                {"keyword": "wireless headphones"},
                {"keyword": "wireless earbuds"},
            ]
        }

        generator = KeywordGenerator(alphashop_client=mock_client)

        results = await generator.expand_keyword(
            keyword="wireless earbuds",
            region="US",
            limit=20,
        )

        assert len(results) == 3
        assert "bluetooth earbuds" in results
        assert "true wireless earbuds" in results
        assert "wireless earbuds" not in results

    @pytest.mark.asyncio
    async def test_generate_selection_keywords_expands_top_keywords(self):
        """Test selection keyword generation expands top keywords."""
        mock_client = AsyncMock()
        mock_client.search_keywords.side_effect = [
            {
                "keyword_list": [
                    {
                        "keyword": "wireless earbuds",
                        "searchVolume": 5000,
                        "oppScore": 75,
                        "searchRank": 1000,
                    },
                    {
                        "keyword": "bluetooth speaker",
                        "searchVolume": 4000,
                        "oppScore": 65,
                        "searchRank": 3000,
                    },
                ]
            },
            {
                "keyword_list": [
                    {"keyword": "noise cancelling earbuds"},
                    {"keyword": "sports earbuds"},
                ]
            },
        ]

        generator = KeywordGenerator(alphashop_client=mock_client)

        results = await generator.generate_selection_keywords(
            category="electronics",
            region="US",
            limit=10,
            expand_top_n=1,
        )

        keywords = [r.keyword for r in results]
        assert "wireless earbuds" in keywords
        assert "bluetooth speaker" in keywords
        assert "noise cancelling earbuds" in keywords
        assert "sports earbuds" in keywords

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cache hit scenario."""
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

        assert len(results) == 1
        assert results[0].keyword == "wireless earbuds"
        assert results[0].search_volume == 5000
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_and_save(self):
        """Test cache miss and save scenario."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True

        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "wireless earbuds",
                    "searchVolume": 5000,
                    "oppScore": 75,
                    "searchRank": 3000,
                }
            ]
        }

        generator = KeywordGenerator(
            redis_client=mock_redis,
            enable_cache=True,
            alphashop_client=mock_client,
        )

        results = await generator.generate_trending_keywords(
            category="electronics",
            region="US",
            limit=10,
        )

        assert len(results) == 1
        assert results[0].keyword == "wireless earbuds"
        mock_redis.get.assert_called_once()
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 86400

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """Test with caching disabled."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "wireless earbuds",
                    "searchVolume": 5000,
                    "oppScore": 75,
                    "searchRank": 3000,
                }
            ]
        }

        generator = KeywordGenerator(
            enable_cache=False,
            alphashop_client=mock_client,
        )

        results = await generator.generate_trending_keywords(
            category="electronics",
            region="US",
            limit=10,
        )

        assert len(results) == 1
        assert results[0].keyword == "wireless earbuds"
        assert generator.redis_client is None

    @pytest.mark.asyncio
    async def test_close_closes_owned_client_only(self):
        """Test close only closes owned AlphaShop client."""
        injected_client = AsyncMock()
        generator = KeywordGenerator(alphashop_client=injected_client)
        await generator.close()
        injected_client.close.assert_not_called()

        owned_client = AsyncMock()
        generator = KeywordGenerator()
        generator._alphashop_client = owned_client
        generator._created_client = True
        await generator.close()
        owned_client.close.assert_called_once()


@pytest.mark.integration
class TestKeywordGeneratorIntegration:
    """Integration tests for KeywordGenerator with real provider chain.

    These tests require external provider access and may fall back depending on
    environment configuration.
    """

    @pytest.mark.asyncio
    async def test_generate_trending_keywords_integration(self):
        """Test real keyword generation path returns usable results."""
        generator = KeywordGenerator(min_trend_score=10)

        results = await generator.generate_trending_keywords(
            category="electronics",
            region="US",
            limit=10,
        )

        assert len(results) > 0
        for result in results:
            assert result.keyword
            assert result.search_volume > 0
            assert result.trend_score >= 10
            assert result.competition_density in ["low", "medium", "high"]

    @pytest.mark.asyncio
    async def test_expand_keyword_integration(self):
        """Test real keyword expansion path."""
        generator = KeywordGenerator()

        related = await generator.expand_keyword(
            keyword="iphone",
            region="US",
            limit=20,
        )

        assert isinstance(related, list)
