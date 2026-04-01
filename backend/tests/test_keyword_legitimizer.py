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
        assert results[2].match_type in ["related", "fallback"]

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
