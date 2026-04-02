"""Tests for keyword legitimizer service."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.keyword_legitimizer import KeywordLegitimizerService, ValidKeyword
from app.services.seed_pool_builder import Seed


class TestKeywordLegitimizerService:
    """Test KeywordLegitimizerService."""

    @pytest.mark.asyncio
    async def test_legitimize_seeds_success(self):
        """Test successful seed legitimization."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "wireless charger",
                    "oppScore": 75,
                    "searchVolume": 5000,
                }
            ]
        }

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(
                term="wireless charger",
                source="user",
                confidence=1.0,
                category="electronics",
                region="US",
                platform="amazon",
            )
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert len(results) == 1
        assert results[0].matched_keyword == "wireless charger"
        assert results[0].report_keyword == "wireless charger"
        assert results[0].match_type == "exact"
        assert results[0].opp_score == 75
        assert results[0].search_volume == 5000
        assert results[0].is_valid_for_report is True

    @pytest.mark.asyncio
    async def test_legitimize_seeds_filters_low_opp_score(self):
        """Test legitimization filters out low opportunity scores."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "generic electronics",
                    "oppScore": 10,
                    "searchVolume": 1000,
                }
            ]
        }

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(
                term="generic electronics",
                source="user",
                confidence=1.0,
                category="electronics",
                region="US",
                platform="amazon",
            )
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert len(results) == 1
        assert results[0].is_valid_for_report is False
        assert results[0].competition_density == "high"

    @pytest.mark.asyncio
    async def test_legitimize_seeds_handles_no_results(self):
        """Test legitimization handles empty keyword list."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {"keyword_list": []}

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(
                term="obscure term",
                source="user",
                confidence=1.0,
                category="electronics",
                region="US",
                platform="amazon",
            )
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_legitimize_seeds_match_types(self):
        """Test legitimization identifies different match types."""
        mock_client = AsyncMock()
        mock_client.search_keywords.side_effect = [
            {"keyword_list": [{"keyword": "phone case", "oppScore": 70, "searchVolume": 4000}]},
            {"keyword_list": [{"keyword": "phone cases", "oppScore": 65, "searchVolume": 3500}]},
            {"keyword_list": [{"keyword": "wireless phone charger", "oppScore": 60, "searchVolume": 3000}]},
        ]

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(term="phone case", source="user", confidence=1.0),
            Seed(term="phone case", source="user", confidence=1.0),
            Seed(term="phone", source="user", confidence=1.0),
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert results[0].match_type == "exact"
        assert results[1].match_type == "normalized"
        # Related/fallback matches are no longer valid for report
        assert results[2].is_valid_for_report is False

    @pytest.mark.asyncio
    async def test_legitimize_seeds_filters_generic_keywords(self):
        """Test legitimization filters out generic keywords."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "wireless electronics",
                    "oppScore": 80,
                    "searchVolume": 10000,
                }
            ]
        }

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(
                term="electronics",
                source="category_static",
                confidence=0.5,
                category="electronics",
                region="US",
                platform="amazon",
            )
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        # Should mark as invalid for report due to generic pattern
        assert len(results) == 1
        assert results[0].is_valid_for_report is False

    @pytest.mark.asyncio
    async def test_legitimize_seeds_filters_brand_keywords_for_report(self):
        """Test legitimization marks brand-containing keywords invalid for report."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "mini ipad tablet",
                    "oppScore": 65,
                    "searchVolume": 380000,
                }
            ]
        }

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(
                term="ipad tablet",
                source="user",
                confidence=1.0,
                category="electronics",
                region="US",
                platform="amazon",
            )
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert len(results) == 1
        assert results[0].matched_keyword == "mini ipad tablet"
        assert results[0].report_keyword == "mini ipad tablet"
        assert results[0].is_valid_for_report is False

    @pytest.mark.asyncio
    async def test_legitimize_seeds_requires_strict_keyword_field_for_report(self):
        """Test report-safe keywords require AlphaShop's strict `keyword` field."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "title": "wireless charger",
                    "oppScore": 75,
                    "searchVolume": 5000,
                }
            ]
        }

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(
                term="wireless charger",
                source="user",
                confidence=1.0,
                category="electronics",
                region="US",
                platform="amazon",
            )
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert len(results) == 1
        assert results[0].matched_keyword == "wireless charger"
        assert results[0].report_keyword is None
        assert results[0].is_valid_for_report is False

    @pytest.mark.asyncio
    async def test_legitimize_seeds_handles_api_errors(self):
        """Test legitimization handles API errors gracefully."""
        mock_client = AsyncMock()
        mock_client.search_keywords.side_effect = Exception("API error")

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(
                term="phone case",
                source="user",
                confidence=1.0,
                category="electronics",
                region="US",
                platform="amazon",
            )
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_legitimize_seeds_applies_request_spacing(self):
        """Test legitimization waits between sequential AlphaShop keyword requests."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "phone case",
                    "oppScore": 70,
                    "searchVolume": 4000,
                }
            ]
        }

        service = KeywordLegitimizerService(alphashop_client=mock_client)
        service.settings.alphashop_keyword_search_min_interval_ms = 250

        seeds = [
            Seed(term="phone case", source="user", confidence=1.0),
            Seed(term="tablet case", source="user", confidence=1.0),
        ]

        with patch("app.services.keyword_legitimizer.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            results = await service.legitimize_seeds(
                seeds=seeds,
                region="US",
                platform="amazon",
                min_opp_score=20.0,
            )

        assert len(results) == 2
        mock_sleep.assert_awaited_once_with(0.25)


    @pytest.mark.asyncio
    async def test_legitimize_seeds_filters_problematic_report_keywords(self):
        """Test legitimization rejects generic keywords that trigger newproduct.report parameter errors."""
        mock_client = AsyncMock()
        mock_client.search_keywords.side_effect = [
            {"keyword_list": [{"keyword": "phone accessories", "oppScore": 80, "searchVolume": 10000}]},
            {"keyword_list": [{"keyword": "kitchen gadgets", "oppScore": 75, "searchVolume": 8000}]},
            {"keyword_list": [{"keyword": "spring essentials for women", "oppScore": 70, "searchVolume": 6000}]},
        ]

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(term="phone accessories", source="exploration", confidence=0.5),
            Seed(term="kitchen gadgets", source="exploration", confidence=0.5),
            Seed(term="spring essentials for women", source="exploration", confidence=0.5),
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert len(results) == 3
        assert all(result.is_valid_for_report is False for result in results)


    @pytest.mark.asyncio
    async def test_legitimize_seeds_extracts_search_intelligence_fields(self):
        """Test legitimization preserves keyword.search market intelligence fields."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "tablet stand",
                    "keywordCn": "平板支架",
                    "oppScore": 82,
                    "searchVolume": 5000,
                    "salesInfo": {
                        "soldCnt30d": {
                            "value": "13.9w+",
                            "growthRate": {"value": "6.0%", "direction": "UP"},
                        },
                        "soldAmt30d": "123456.7",
                    },
                    "demandInfo": {
                        "searchRank": "# 63.5w+",
                        "rankTrends": [{"searchRank": "635000"}, {"searchRank": 620000}, "610000"],
                    },
                    "radar": {
                        "propertyList": [
                            {"name": "需求分", "value": 88},
                            {"name": "供给分", "value": 52},
                            {"name": "销售分", "value": "73"},
                            {"name": "新品分", "value": 64},
                            {"name": "评价分", "value": 91},
                        ]
                    },
                }
            ]
        }

        service = KeywordLegitimizerService(alphashop_client=mock_client)

        seeds = [
            Seed(
                term="tablet stand",
                source="user",
                confidence=1.0,
                category="electronics",
                region="US",
                platform="amazon",
            )
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert len(results) == 1
        result = results[0]
        assert result.keyword_cn == "平板支架"
        assert result.sold_cnt_30d == 139000
        assert result.sold_amt_30d == 123456.7
        assert result.search_rank == 635000
        assert result.growth_rate == 0.06
        assert result.rank_trends == [635000, 620000, 610000]
        assert result.radar_scores == {
            "demand_score": 88.0,
            "supply_score": 52.0,
            "sales_score": 73.0,
            "newproduct_score": 64.0,
            "review_score": 91.0,
        }
        assert result.to_dict()["keyword_cn"] == "平板支架"

    @pytest.mark.asyncio
    async def test_legitimize_seeds_without_client(self):
        """Test legitimization returns empty when client unavailable."""
        service = KeywordLegitimizerService()

        seeds = [
            Seed(
                term="phone case",
                source="user",
                confidence=1.0,
                category="electronics",
                region="US",
                platform="amazon",
            )
        ]

        results = await service.legitimize_seeds(
            seeds=seeds,
            region="US",
            platform="amazon",
            min_opp_score=20.0,
        )

        assert len(results) == 0
