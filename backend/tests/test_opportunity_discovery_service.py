"""Tests for opportunity discovery service."""
import pytest
from unittest.mock import AsyncMock

from app.services.opportunity_discovery_service import (
    OpportunityDiscoveryService,
    OpportunityDraft,
)
from app.services.keyword_legitimizer import ValidKeyword
from app.services.seed_pool_builder import Seed


class TestOpportunityDiscoveryService:
    """Test OpportunityDiscoveryService."""

    @pytest.mark.asyncio
    async def test_discover_opportunities_success(self):
        """Test successful opportunity discovery."""
        mock_client = AsyncMock()
        mock_client.newproduct_report.return_value = {
            "product_list": [
                {"productId": "p1", "title": "Product 1"},
                {"productId": "p2", "title": "Product 2"},
            ],
            "keyword_summary": {
                "summary": "Rising demand product",
                "opportunityScore": 85,
            },
            "request_id": "req-123",
            "raw": {},
        }

        service = OpportunityDiscoveryService(alphashop_client=mock_client)

        seed = Seed(term="phone case", source="user", confidence=1.0)
        valid_keywords = [
            ValidKeyword(
                seed=seed,
                matched_keyword="phone case",
                match_type="exact",
                opp_score=75.0,
                search_volume=5000,
                competition_density="low",
                is_valid_for_report=True,
                raw={},
                report_keyword="phone case",
            )
        ]

        opportunities = await service.discover_opportunities(
            valid_keywords=valid_keywords,
            region="US",
            platform="amazon",
            max_reports=5,
            report_size=10,
        )

        assert len(opportunities) == 1
        assert opportunities[0].keyword == "phone case"
        assert opportunities[0].opportunity_score == 85
        assert len(opportunities[0].product_list) == 2

    @pytest.mark.asyncio
    async def test_discover_opportunities_uses_report_keyword_for_api_calls(self):
        """Test newproduct.report uses strict keyword.search `keyword` field."""
        mock_client = AsyncMock()
        mock_client.newproduct_report.return_value = {
            "product_list": [{"productId": "p1", "title": "Product 1"}],
            "keyword_summary": {"opportunityScore": 80},
            "request_id": "req-123",
            "raw": {},
        }

        service = OpportunityDiscoveryService(alphashop_client=mock_client)

        seed = Seed(term="ipad tablet", source="user", confidence=1.0)
        valid_keywords = [
            ValidKeyword(
                seed=seed,
                matched_keyword="mini ipad tablet",
                match_type="related",
                opp_score=75.0,
                search_volume=5000,
                competition_density="low",
                is_valid_for_report=True,
                raw={"keyword": "tablet stand"},
                report_keyword="tablet stand",
            )
        ]

        opportunities = await service.discover_opportunities(
            valid_keywords=valid_keywords,
            region="US",
            platform="amazon",
            max_reports=5,
            report_size=10,
        )

        assert len(opportunities) == 1
        mock_client.newproduct_report.assert_awaited_once_with(
            platform="amazon",
            region="US",
            product_keyword="tablet stand",
        )

    @pytest.mark.asyncio
    async def test_discover_opportunities_skips_missing_report_keyword(self):
        """Test opportunity discovery skips report-safe items missing strict report keyword."""
        mock_client = AsyncMock()

        service = OpportunityDiscoveryService(alphashop_client=mock_client)

        seed = Seed(term="phone case", source="user", confidence=1.0)
        valid_keywords = [
            ValidKeyword(
                seed=seed,
                matched_keyword="phone case",
                match_type="exact",
                opp_score=75.0,
                search_volume=5000,
                competition_density="low",
                is_valid_for_report=True,
                raw={},
                report_keyword=None,
            )
        ]

        opportunities = await service.discover_opportunities(
            valid_keywords=valid_keywords,
            region="US",
            platform="amazon",
            max_reports=5,
            report_size=10,
        )

        assert len(opportunities) == 0
        mock_client.newproduct_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_opportunities_filters_invalid_keywords(self):
        """Test opportunity discovery filters out invalid keywords."""
        mock_client = AsyncMock()

        service = OpportunityDiscoveryService(alphashop_client=mock_client)

        seed = Seed(term="generic", source="user", confidence=1.0)
        valid_keywords = [
            ValidKeyword(
                seed=seed,
                matched_keyword="generic electronics",
                match_type="exact",
                opp_score=10.0,
                search_volume=1000,
                competition_density="high",
                is_valid_for_report=False,
                raw={},
                report_keyword="generic electronics",
            )
        ]

        opportunities = await service.discover_opportunities(
            valid_keywords=valid_keywords,
            region="US",
            platform="amazon",
            max_reports=5,
            report_size=10,
        )

        assert len(opportunities) == 0
        mock_client.newproduct_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_opportunities_handles_empty_product_list(self):
        """Test opportunity discovery handles empty product lists."""
        mock_client = AsyncMock()
        mock_client.newproduct_report.return_value = {
            "product_list": [],
            "keyword_summary": {},
            "request_id": "req-123",
            "raw": {},
        }

        service = OpportunityDiscoveryService(alphashop_client=mock_client)

        seed = Seed(term="obscure product", source="user", confidence=1.0)
        valid_keywords = [
            ValidKeyword(
                seed=seed,
                matched_keyword="obscure product",
                match_type="exact",
                opp_score=50.0,
                search_volume=2000,
                competition_density="low",
                is_valid_for_report=True,
                raw={},
                report_keyword="obscure product",
            )
        ]

        opportunities = await service.discover_opportunities(
            valid_keywords=valid_keywords,
            region="US",
            platform="amazon",
            max_reports=5,
            report_size=10,
        )

        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_discover_opportunities_sorts_by_score(self):
        """Test opportunities are sorted by score descending."""
        mock_client = AsyncMock()
        mock_client.newproduct_report.side_effect = [
            {
                "product_list": [{"productId": "p1"}],
                "keyword_summary": {"opportunityScore": 60},
                "request_id": "req-1",
                "raw": {},
            },
            {
                "product_list": [{"productId": "p2"}],
                "keyword_summary": {"opportunityScore": 90},
                "request_id": "req-2",
                "raw": {},
            },
        ]

        service = OpportunityDiscoveryService(alphashop_client=mock_client)

        seed1 = Seed(term="keyword1", source="user", confidence=1.0)
        seed2 = Seed(term="keyword2", source="user", confidence=1.0)
        valid_keywords = [
            ValidKeyword(
                seed=seed1,
                matched_keyword="keyword1",
                match_type="exact",
                opp_score=60.0,
                search_volume=3000,
                competition_density="low",
                is_valid_for_report=True,
                raw={},
                report_keyword="keyword1",
            ),
            ValidKeyword(
                seed=seed2,
                matched_keyword="keyword2",
                match_type="exact",
                opp_score=90.0,
                search_volume=5000,
                competition_density="low",
                is_valid_for_report=True,
                raw={},
                report_keyword="keyword2",
            ),
        ]

        opportunities = await service.discover_opportunities(
            valid_keywords=valid_keywords,
            region="US",
            platform="amazon",
            max_reports=5,
            report_size=10,
        )

        assert len(opportunities) == 2
        assert opportunities[0].opportunity_score == 90
        assert opportunities[1].opportunity_score == 60

    @pytest.mark.asyncio
    async def test_discover_opportunities_respects_max_reports(self):
        """Test opportunity discovery respects max_reports limit."""
        mock_client = AsyncMock()

        service = OpportunityDiscoveryService(alphashop_client=mock_client)

        seeds = [Seed(term=f"kw{i}", source="user", confidence=1.0) for i in range(10)]
        valid_keywords = [
            ValidKeyword(
                seed=seed,
                matched_keyword=seed.term,
                match_type="exact",
                opp_score=70.0 + i,
                search_volume=5000,
                competition_density="low",
                is_valid_for_report=True,
                raw={},
                report_keyword=seed.term,
            )
            for i, seed in enumerate(seeds)
        ]

        await service.discover_opportunities(
            valid_keywords=valid_keywords,
            region="US",
            platform="amazon",
            max_reports=3,
            report_size=10,
        )

        # Should only call API 3 times
        assert mock_client.newproduct_report.call_count == 3

    @pytest.mark.asyncio
    async def test_discover_opportunities_handles_api_errors(self):
        """Test opportunity discovery handles API errors gracefully."""
        mock_client = AsyncMock()
        mock_client.newproduct_report.side_effect = Exception("API error")

        service = OpportunityDiscoveryService(alphashop_client=mock_client)

        seed = Seed(term="phone case", source="user", confidence=1.0)
        valid_keywords = [
            ValidKeyword(
                seed=seed,
                matched_keyword="phone case",
                match_type="exact",
                opp_score=75.0,
                search_volume=5000,
                competition_density="low",
                is_valid_for_report=True,
                raw={},
                report_keyword="phone case",
            )
        ]

        opportunities = await service.discover_opportunities(
            valid_keywords=valid_keywords,
            region="US",
            platform="amazon",
            max_reports=5,
            report_size=10,
        )

        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_discover_opportunities_without_client(self):
        """Test opportunity discovery returns empty when client unavailable."""
        service = OpportunityDiscoveryService()

        seed = Seed(term="phone case", source="user", confidence=1.0)
        valid_keywords = [
            ValidKeyword(
                seed=seed,
                matched_keyword="phone case",
                match_type="exact",
                opp_score=75.0,
                search_volume=5000,
                competition_density="low",
                is_valid_for_report=True,
                raw={},
                report_keyword="phone case",
            )
        ]

        opportunities = await service.discover_opportunities(
            valid_keywords=valid_keywords,
            region="US",
            platform="amazon",
            max_reports=5,
            report_size=10,
        )

        assert len(opportunities) == 0
