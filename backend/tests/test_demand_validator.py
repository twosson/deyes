"""Tests for demand validator service."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.services.demand_validator import (
    CompetitionDensity,
    DemandValidationResult,
    DemandValidator,
    TrendDirection,
)


class TestDemandValidationResult:
    """Test DemandValidationResult dataclass."""

    def test_passed_with_good_metrics(self):
        """Test validation passes with good metrics."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=2000,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_rejected_low_search_volume(self):
        """Test validation fails with low search volume."""
        result = DemandValidationResult(
            keyword="obscure product",
            search_volume=100,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.STABLE,
            trend_growth_rate=Decimal("0.05"),
        )

        assert result.passed is False
        assert "Search volume too low" in result.rejection_reasons[0]

    def test_rejected_high_competition(self):
        """Test validation fails with high competition."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=5000,
            competition_density=CompetitionDensity.HIGH,
            trend_direction=TrendDirection.STABLE,
            trend_growth_rate=Decimal("0.05"),
        )

        assert result.passed is False
        assert "Competition density too high" in result.rejection_reasons[0]

    def test_rejected_declining_trend(self):
        """Test validation fails with declining trend."""
        result = DemandValidationResult(
            keyword="fidget spinner",
            search_volume=2000,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.DECLINING,
            trend_growth_rate=Decimal("-0.30"),
        )

        assert result.passed is False
        assert "Market trend declining" in result.rejection_reasons[0]

    def test_multiple_rejection_reasons(self):
        """Test validation fails with multiple reasons."""
        result = DemandValidationResult(
            keyword="bad product",
            search_volume=100,
            competition_density=CompetitionDensity.HIGH,
            trend_direction=TrendDirection.DECLINING,
            trend_growth_rate=Decimal("-0.30"),
        )

        assert result.passed is False
        assert len(result.rejection_reasons) == 3

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=2000,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            hot_sell_rank=5,
            repurchase_rate=Decimal("0.35"),
            lead_time_days=7,
        )

        result_dict = result.to_dict()

        assert result_dict["keyword"] == "phone case"
        assert result_dict["search_volume"] == 2000
        assert result_dict["competition_density"] == "low"
        assert result_dict["trend_direction"] == "rising"
        assert result_dict["trend_growth_rate"] == 0.25
        assert result_dict["hot_sell_rank"] == 5
        assert result_dict["repurchase_rate"] == 0.35
        assert result_dict["lead_time_days"] == 7
        assert result_dict["passed"] is True


class TestDemandValidator:
    """Test DemandValidator service."""

    def test_init_default(self):
        """Test initialization with defaults."""
        validator = DemandValidator()

        assert validator.min_search_volume == 500
        assert validator.use_helium10 is False
        assert validator.helium10_api_key is None

    def test_init_custom(self):
        """Test initialization with custom values."""
        validator = DemandValidator(
            min_search_volume=1000,
            use_helium10=True,
            helium10_api_key="test_key",
        )

        assert validator.min_search_volume == 1000
        assert validator.use_helium10 is True
        assert validator.helium10_api_key == "test_key"

    def test_init_helium10_without_key(self):
        """Test initialization disables Helium 10 when no API key is provided."""
        validator = DemandValidator(
            use_helium10=True,
            helium10_api_key=None,
        )

        assert validator.use_helium10 is False

    def test_region_to_geo(self):
        """Test region code conversion."""
        validator = DemandValidator()

        assert validator._region_to_geo("US") == "US"
        assert validator._region_to_geo("UK") == "GB"
        assert validator._region_to_geo("GB") == "GB"
        assert validator._region_to_geo("JP") == "JP"
        assert validator._region_to_geo("") == "US"
        assert validator._region_to_geo(None) == "US"

    def test_region_to_marketplace(self):
        """Test region to marketplace conversion."""
        validator = DemandValidator()

        assert validator._region_to_marketplace("US") == "US"
        assert validator._region_to_marketplace("UK") == "UK"
        assert validator._region_to_marketplace("GB") == "UK"
        assert validator._region_to_marketplace("JP") == "JP"
        assert validator._region_to_marketplace("") == "US"
        assert validator._region_to_marketplace(None) == "US"

    def test_estimate_search_volume_from_interest(self):
        """Test search volume estimation from interest."""
        validator = DemandValidator()

        assert validator._estimate_search_volume_from_interest(80) == 10000
        assert validator._estimate_search_volume_from_interest(60) == 5000
        assert validator._estimate_search_volume_from_interest(40) == 2000
        assert validator._estimate_search_volume_from_interest(20) == 500
        assert validator._estimate_search_volume_from_interest(7) == 200
        assert validator._estimate_search_volume_from_interest(2) == 100

    def test_classify_trend_direction(self):
        """Test trend direction classification."""
        validator = DemandValidator()

        assert validator._classify_trend_direction(Decimal("0.30")) == TrendDirection.RISING
        assert validator._classify_trend_direction(Decimal("0.20")) == TrendDirection.RISING
        assert validator._classify_trend_direction(Decimal("0.10")) == TrendDirection.STABLE
        assert validator._classify_trend_direction(Decimal("0.00")) == TrendDirection.STABLE
        assert validator._classify_trend_direction(Decimal("-0.10")) == TrendDirection.STABLE
        assert validator._classify_trend_direction(Decimal("-0.20")) == TrendDirection.DECLINING
        assert validator._classify_trend_direction(Decimal("-0.30")) == TrendDirection.DECLINING

    @pytest.mark.asyncio
    async def test_validate_with_mock_trends(self):
        """Test validate method with mocked provider trend signals."""
        validator = DemandValidator(min_search_volume=500)

        # Mock the _get_search_trends method
        with patch.object(
            validator,
            "_get_search_trends",
            return_value=(2000, Decimal("0.25"), TrendDirection.RISING),
        ):
            with patch.object(
                validator,
                "_assess_competition_density",
                return_value=CompetitionDensity.LOW,
            ):
                result = await validator.validate(
                    keyword="phone case",
                    category="electronics",
                    region="US",
                )

        assert result.keyword == "phone case"
        assert result.search_volume == 2000
        assert result.competition_density == CompetitionDensity.LOW
        assert result.trend_direction == TrendDirection.RISING
        assert result.trend_growth_rate == Decimal("0.25")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_batch(self):
        """Test batch validation."""
        validator = DemandValidator(min_search_volume=500)

        keywords = ["phone case", "wireless charger", "bluetooth speaker"]

        # Mock the validate method
        with patch.object(
            validator,
            "validate",
            side_effect=[
                DemandValidationResult(
                    keyword="phone case",
                    search_volume=2000,
                    competition_density=CompetitionDensity.LOW,
                    trend_direction=TrendDirection.RISING,
                    trend_growth_rate=Decimal("0.25"),
                ),
                DemandValidationResult(
                    keyword="wireless charger",
                    search_volume=100,
                    competition_density=CompetitionDensity.LOW,
                    trend_direction=TrendDirection.STABLE,
                    trend_growth_rate=Decimal("0.05"),
                ),
                DemandValidationResult(
                    keyword="bluetooth speaker",
                    search_volume=3000,
                    competition_density=CompetitionDensity.HIGH,
                    trend_direction=TrendDirection.STABLE,
                    trend_growth_rate=Decimal("0.10"),
                ),
            ],
        ):
            results = await validator.validate_batch(
                keywords=keywords,
                category="electronics",
                region="US",
            )

        assert len(results) == 3
        assert results[0].passed is True
        assert results[1].passed is False  # Low search volume
        assert results[2].passed is False  # High competition

    def test_build_cache_key(self):
        """Test cache key building."""
        validator = DemandValidator()

        key1 = validator._build_cache_key("phone case", "US")
        key2 = validator._build_cache_key("phone case", "UK")
        key3 = validator._build_cache_key("wireless charger", "US")

        # Same keyword + region should produce same key
        assert key1 == validator._build_cache_key("phone case", "US")

        # Different region should produce different key
        assert key1 != key2

        # Different keyword should produce different key
        assert key1 != key3

        # Key should have expected format
        assert key1.startswith("demand_validation:")
        assert ":US" in key1

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cache hit scenario."""
        # Create mock Redis client
        mock_redis = AsyncMock()
        cached_result = DemandValidationResult(
            keyword="phone case",
            search_volume=2000,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
        )
        mock_redis.get.return_value = json.dumps(cached_result.to_dict())

        validator = DemandValidator(
            min_search_volume=500,
            redis_client=mock_redis,
            enable_cache=True,
        )

        result = await validator.validate(
            keyword="phone case",
            category="electronics",
            region="US",
        )

        # Should get cached result
        assert result.keyword == "phone case"
        assert result.search_volume == 2000
        assert result.passed is True

        # Should have called Redis get
        mock_redis.get.assert_called_once()

        # Should NOT have called _get_search_trends (cache hit)
        # This is verified by not mocking _get_search_trends

    @pytest.mark.asyncio
    async def test_cache_miss_and_save(self):
        """Test cache miss and save scenario."""
        # Create mock Redis client
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss
        mock_redis.set.return_value = True

        validator = DemandValidator(
            min_search_volume=500,
            redis_client=mock_redis,
            enable_cache=True,
        )

        # Mock the _get_search_trends method
        with patch.object(
            validator,
            "_get_search_trends",
            return_value=(2000, Decimal("0.25"), TrendDirection.RISING),
        ):
            with patch.object(
                validator,
                "_assess_competition_density",
                return_value=CompetitionDensity.LOW,
            ):
                result = await validator.validate(
                    keyword="phone case",
                    category="electronics",
                    region="US",
                )

        # Should get fresh result
        assert result.keyword == "phone case"
        assert result.search_volume == 2000
        assert result.passed is True

        # Should have called Redis get (cache miss)
        mock_redis.get.assert_called_once()

        # Should have called Redis set (save to cache)
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 86400  # Default TTL

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """Test with caching disabled."""
        validator = DemandValidator(
            min_search_volume=500,
            enable_cache=False,
        )

        # Mock the _get_search_trends method
        with patch.object(
            validator,
            "_get_search_trends",
            return_value=(2000, Decimal("0.25"), TrendDirection.RISING),
        ):
            with patch.object(
                validator,
                "_assess_competition_density",
                return_value=CompetitionDensity.LOW,
            ):
                result = await validator.validate(
                    keyword="phone case",
                    category="electronics",
                    region="US",
                )

        # Should get result
        assert result.keyword == "phone case"
        assert result.search_volume == 2000

        # Should NOT have created Redis client
        assert validator.redis_client is None

    def test_heuristic_competition_generic_keyword(self):
        """Test heuristic competition for generic keywords."""
        validator = DemandValidator()

        # Generic keywords (1-2 words) should be HIGH
        assert validator._heuristic_competition_assessment("phone") == CompetitionDensity.HIGH
        assert validator._heuristic_competition_assessment("laptop") == CompetitionDensity.HIGH

    def test_heuristic_competition_specific_keyword(self):
        """Test heuristic competition for specific keywords."""
        validator = DemandValidator()

        # Specific keywords (3-4 words) should be MEDIUM
        assert validator._heuristic_competition_assessment("wireless phone charger") == CompetitionDensity.MEDIUM
        assert validator._heuristic_competition_assessment("blue running shoes men") == CompetitionDensity.MEDIUM

    def test_heuristic_competition_long_tail_keyword(self):
        """Test heuristic competition for long-tail keywords."""
        validator = DemandValidator()

        # Long-tail keywords (5+ words) should be LOW
        assert validator._heuristic_competition_assessment(
            "waterproof wireless phone charger for car"
        ) == CompetitionDensity.LOW
        assert validator._heuristic_competition_assessment(
            "blue running shoes for men size 10"
        ) == CompetitionDensity.LOW

    def test_heuristic_competition_brand_names(self):
        """Test heuristic competition for brand names."""
        validator = DemandValidator()

        # Brand names should be HIGH regardless of word count
        assert validator._heuristic_competition_assessment("iphone case") == CompetitionDensity.HIGH
        assert validator._heuristic_competition_assessment("nike shoes") == CompetitionDensity.HIGH
        assert validator._heuristic_competition_assessment("samsung galaxy phone") == CompetitionDensity.HIGH

    @pytest.mark.asyncio
    async def test_competition_assessment_with_legacy_fallback(self):
        """Test competition assessment falls back to heuristic when all providers are unavailable."""
        validator = DemandValidator()

        # Mock pytrends to return high interest
        with patch("app.services.demand_validator.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = CompetitionDensity.HIGH

            result = await validator._assess_competition_density(
                keyword="phone",
                region="US",
            )

        assert result == CompetitionDensity.HIGH


class TestDemandValidatorAlphaShop:
    """Test AlphaShop-first demand validation behavior."""

    def test_extract_search_volume_from_alphashop(self):
        """Test AlphaShop search volume mapping."""
        validator = DemandValidator()

        assert validator._extract_search_volume_from_alphashop({"searchVolume": 3000}) == 3000
        assert validator._extract_search_volume_from_alphashop({"salesInfo": {"searchVolume": 2500}}) == 2500
        assert validator._extract_search_volume_from_alphashop({"soldCnt30d": 400}) == 4000
        assert validator._extract_search_volume_from_alphashop({"searchRank": 800}) == 10000
        assert validator._extract_search_volume_from_alphashop({"searchRank": 7000}) == 2000
        assert validator._extract_search_volume_from_alphashop({"oppScore": 60}) == 5000
        assert validator._extract_search_volume_from_alphashop({"salesInfo": {"soldCnt30d": {"value": "13.9w+"}}}) == 1390000
        assert validator._extract_search_volume_from_alphashop({"demandInfo": {"searchRank": "# 99.6w+"}}) == 500

    def test_extract_trend_from_alphashop_rank_trends(self):
        """Test AlphaShop trend extraction from rank trends."""
        validator = DemandValidator()

        growth_rate, direction = validator._extract_trend_from_alphashop(
            {"demandInfo": {"rankTrends": [{"y": 100}, {"y": 80}, {"y": 50}, {"y": 40}]}}
        )

        assert growth_rate == Decimal("0.5")
        assert direction == TrendDirection.RISING

    def test_extract_trend_from_alphashop_opp_score(self):
        """Test AlphaShop trend extraction from opportunity score."""
        validator = DemandValidator()

        growth_rate, direction = validator._extract_trend_from_alphashop({"oppScore": 75})
        assert growth_rate == Decimal("0.25")
        assert direction == TrendDirection.RISING

        growth_rate, direction = validator._extract_trend_from_alphashop({"oppScore": 50})
        assert growth_rate == Decimal("0.05")
        assert direction == TrendDirection.STABLE

        growth_rate, direction = validator._extract_trend_from_alphashop({"oppScore": 20})
        assert growth_rate == Decimal("-0.10")
        assert direction == TrendDirection.DECLINING

    def test_extract_trend_from_alphashop_prefers_growth_rate(self):
        """Test AlphaShop trend extraction prefers explicit growthRate over rank trends."""
        validator = DemandValidator()

        growth_rate, direction = validator._extract_trend_from_alphashop(
            {
                "demandInfo": {"rankTrends": [{"y": 560}, {"y": 536}, {"y": 611}, {"y": 958}]},
                "salesInfo": {
                    "soldCnt30d": {
                        "growthRate": {
                            "value": "5.0%",
                            "direction": "UP",
                        }
                    }
                },
            }
        )

        assert growth_rate == Decimal("0.05")
        assert direction == TrendDirection.RISING

    def test_extract_rank_trends(self):
        """Test AlphaShop rank trend extraction helper."""
        validator = DemandValidator()

        result = validator._extract_rank_trends(
            {"rankTrends": [100, "200", {"rank": 300}, {"value": 400}, {"searchRank": 500}, {"y": 600}, "bad"]}
        )

        assert result == [100, 200, 300, 400, 500, 600]

    @pytest.mark.asyncio
    async def test_get_trends_from_alphashop(self):
        """Test AlphaShop trend lookup returns mapped demand signals."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "phone case",
                    "searchVolume": 3200,
                    "rankTrends": [100, 80, 50, 40],
                }
            ]
        }

        validator = DemandValidator(alphashop_client=mock_client)

        volume, growth_rate, direction = await validator._get_trends_from_alphashop(
            keyword="phone case",
            region="US",
        )

        assert volume == 3200
        assert growth_rate == Decimal("0.5")
        assert direction == TrendDirection.RISING

    @pytest.mark.asyncio
    async def test_get_trends_from_alphashop_prefers_exact_match(self):
        """Test AlphaShop trend lookup prefers exact keyword match over first result."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [
                {
                    "keyword": "wireless electronics",
                    "searchVolume": 9999,
                    "rankTrends": [500, 500, 500, 500],
                },
                {
                    "keyword": "wireless earbuds",
                    "searchVolume": 3200,
                    "rankTrends": [100, 80, 50, 40],
                },
            ]
        }

        validator = DemandValidator(alphashop_client=mock_client)

        volume, growth_rate, direction = await validator._get_trends_from_alphashop(
            keyword="wireless earbuds",
            region="US",
        )

        assert volume == 3200
        assert growth_rate == Decimal("0.5")
        assert direction == TrendDirection.RISING

    @pytest.mark.asyncio
    async def test_get_trends_from_alphashop_without_client(self):
        """Test AlphaShop trend lookup degrades cleanly when client is unavailable."""
        validator = DemandValidator()

        with patch.object(validator, "_get_alphashop_client", new_callable=AsyncMock) as mock_get_client:
            mock_get_client.return_value = None
            volume, growth_rate, direction = await validator._get_trends_from_alphashop(
                keyword="phone case",
                region="US",
            )

        assert volume is None
        assert growth_rate is None
        assert direction == TrendDirection.UNKNOWN

    @pytest.mark.asyncio
    async def test_get_search_trends_prefers_alphashop(self):
        """Test provider priority uses AlphaShop before Helium 10 and pytrends."""
        validator = DemandValidator(use_helium10=True, helium10_api_key="test_key")

        with patch.object(
            validator,
            "_get_trends_from_alphashop",
            new_callable=AsyncMock,
            return_value=(3000, Decimal("0.30"), TrendDirection.RISING),
        ) as mock_alpha:
            with patch.object(
                validator,
                "_get_trends_from_helium10",
                new_callable=AsyncMock,
            ) as mock_helium10:
                with patch.object(
                    validator,
                    "_get_trends_from_pytrends",
                    new_callable=AsyncMock,
                ) as mock_pytrends:
                    result = await validator._get_search_trends("phone case", "US")

        assert result == (3000, Decimal("0.30"), TrendDirection.RISING)
        mock_alpha.assert_called_once()
        mock_helium10.assert_not_called()
        mock_pytrends.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_search_trends_falls_back_to_helium10(self):
        """Test provider priority falls back to Helium 10 when AlphaShop is unavailable."""
        validator = DemandValidator(use_helium10=True, helium10_api_key="test_key")

        with patch.object(
            validator,
            "_get_trends_from_alphashop",
            new_callable=AsyncMock,
            return_value=(None, None, TrendDirection.UNKNOWN),
        ) as mock_alpha:
            with patch.object(
                validator,
                "_get_trends_from_helium10",
                new_callable=AsyncMock,
                return_value=(2200, Decimal("0.20"), TrendDirection.RISING),
            ) as mock_helium10:
                with patch.object(
                    validator,
                    "_get_trends_from_pytrends",
                    new_callable=AsyncMock,
                ) as mock_pytrends:
                    result = await validator._get_search_trends("phone case", "US")

        assert result == (2200, Decimal("0.20"), TrendDirection.RISING)
        mock_alpha.assert_called_once()
        mock_helium10.assert_called_once()
        mock_pytrends.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_search_trends_falls_back_to_pytrends(self):
        """Test provider priority reaches legacy pytrends fallback when needed."""
        validator = DemandValidator(use_helium10=True, helium10_api_key="test_key")

        with patch.object(
            validator,
            "_get_trends_from_alphashop",
            new_callable=AsyncMock,
            return_value=(None, None, TrendDirection.UNKNOWN),
        ) as mock_alpha:
            with patch.object(
                validator,
                "_get_trends_from_helium10",
                new_callable=AsyncMock,
                return_value=(None, None, TrendDirection.UNKNOWN),
            ) as mock_helium10:
                with patch.object(
                    validator,
                    "_get_trends_from_pytrends",
                    new_callable=AsyncMock,
                    return_value=(1500, Decimal("0.15"), TrendDirection.STABLE),
                ) as mock_pytrends:
                    result = await validator._get_search_trends("phone case", "US")

        assert result == (1500, Decimal("0.15"), TrendDirection.STABLE)
        mock_alpha.assert_called_once()
        mock_helium10.assert_called_once()
        mock_pytrends.assert_called_once()

    @pytest.mark.asyncio
    async def test_assess_competition_density_from_alphashop_search_rank(self):
        """Test competition density uses AlphaShop search rank when available."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [{"demandInfo": {"searchRank": "# 500+"}}]
        }
        validator = DemandValidator(alphashop_client=mock_client)

        result = await validator._assess_competition_density("phone case", "US")

        assert result == CompetitionDensity.HIGH

    @pytest.mark.asyncio
    async def test_assess_competition_density_from_alphashop_opp_score(self):
        """Test competition density uses AlphaShop opportunity score when rank is absent."""
        mock_client = AsyncMock()
        mock_client.search_keywords.return_value = {
            "keyword_list": [{"oppScore": 30}]
        }
        validator = DemandValidator(alphashop_client=mock_client)

        result = await validator._assess_competition_density("phone case", "US")

        assert result == CompetitionDensity.LOW

    @pytest.mark.asyncio
    async def test_validate_legitimized_batch_reuses_raw_metrics_without_refetch(self):
        """Test legitimized batch validation reuses AlphaShop raw metrics instead of refetching."""
        from app.services.keyword_legitimizer import ValidKeyword
        from app.services.seed_pool_builder import Seed

        mock_client = AsyncMock()
        validator = DemandValidator(alphashop_client=mock_client)

        valid_keyword = ValidKeyword(
            seed=Seed(term="ipad tablet", source="user", confidence=1.0),
            matched_keyword="mini ipad tablet",
            match_type="related",
            opp_score=38.7,
            search_volume=None,
            competition_density="medium",
            is_valid_for_report=True,
            raw={
                "keyword": "mini ipad tablet",
                "oppScore": "38.7",
                "salesInfo": {
                    "soldCnt30d": {
                        "growthRate": {
                            "value": "6.0%",
                            "direction": "UP",
                        },
                        "value": "3.8w+",
                    }
                },
                "demandInfo": {
                    "searchRank": "# 63.5w+",
                    "rankTrends": [
                        {"x": "202511", "y": 570099.0},
                        {"x": "202512", "y": 551712.0},
                        {"x": "202601", "y": 726962.0},
                        {"x": "202602", "y": 635588.0},
                    ],
                },
            },
            report_keyword="mini ipad tablet",
        )

        with patch.object(validator, "_get_search_trends", new_callable=AsyncMock) as mock_get_trends:
            results = await validator.validate_legitimized_batch(
                valid_keywords=[valid_keyword],
                category="electronics",
                region="US",
                platform="temu",
            )

        assert len(results) == 1
        assert results[0].keyword == "mini ipad tablet"
        assert results[0].search_volume == 380000
        assert results[0].trend_direction == TrendDirection.RISING
        assert results[0].trend_growth_rate == Decimal("0.06")
        assert results[0].passed is True
        mock_get_trends.assert_not_awaited()


@pytest.mark.integration
class TestDemandValidatorIntegration:
    """Integration tests for DemandValidator with the real provider chain.

    These tests require external provider access and may fall back depending on
    environment configuration.
    """

    @pytest.mark.asyncio
    async def test_real_keyword_validation(self):
        """Test with real provider chain for a popular keyword."""
        validator = DemandValidator(min_search_volume=100)

        # Use a popular keyword that should have data
        result = await validator.validate(
            keyword="iphone",
            category="electronics",
            region="US",
        )

        # Should have some search volume
        assert result.search_volume is not None
        assert result.search_volume > 0

        # Should have trend data
        assert result.trend_direction in [
            TrendDirection.RISING,
            TrendDirection.STABLE,
            TrendDirection.DECLINING,
        ]

        # Should have growth rate
        assert result.trend_growth_rate is not None

    @pytest.mark.asyncio
    async def test_obscure_keyword_validation(self):
        """Test with obscure keyword that may have no data."""
        validator = DemandValidator(min_search_volume=100)

        # Use a very obscure keyword
        result = await validator.validate(
            keyword="xyzabc123nonexistent",
            category="electronics",
            region="US",
        )

        # Should handle gracefully
        assert result.search_volume is not None
        assert result.trend_direction is not None

    @pytest.mark.asyncio
    async def test_different_regions_validation(self):
        """Test with different regions."""
        validator = DemandValidator(min_search_volume=100)

        regions = ["US", "UK", "JP"]
        results = []

        for region in regions:
            result = await validator.validate(
                keyword="phone",
                category="electronics",
                region=region,
            )
            results.append(result)

        # All should return valid results
        for result in results:
            assert result.search_volume is not None
            assert result.trend_direction is not None


@pytest.mark.asyncio
async def test_provider_fallback_on_import_error():
    """Test fallback to mock data when external providers are unavailable."""
    validator = DemandValidator()

    # Mock ImportError for external providers
    with patch("app.services.demand_validator.asyncio.to_thread") as mock_to_thread:

        def mock_fetch():
            raise ImportError("No module named 'pytrends'")

        mock_to_thread.side_effect = lambda func: func()

        with patch.object(
            validator,
            "_get_trends_from_alphashop",
            return_value=(None, None, TrendDirection.UNKNOWN),
        ):
            result = await validator.validate(
                keyword="phone case",
                category="electronics",
                region="US",
            )

    # Should fallback to heuristic/mock data
    assert result.search_volume is not None
    assert result.trend_direction is not None


class TestRegionSpecificValidation:
    """Test region-specific demand validation thresholds."""

    def test_us_region_uses_default_threshold(self):
        """Test US region uses default 500 search volume threshold."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=600,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_us_region_rejects_below_threshold(self):
        """Test US region rejects below 500 search volume."""
        result = DemandValidationResult(
            keyword="obscure product",
            search_volume=400,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
        )

        assert result.passed is False
        assert any("Search volume too low" in reason for reason in result.rejection_reasons)
        assert "400 < 500" in result.rejection_reasons[0]
        assert "region: US" in result.rejection_reasons[0]

    def test_uk_region_uses_lower_threshold(self):
        """Test UK region uses 350 search volume threshold."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=400,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="UK",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_uk_region_rejects_below_threshold(self):
        """Test UK region rejects below 350 search volume."""
        result = DemandValidationResult(
            keyword="obscure product",
            search_volume=300,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="UK",
        )

        assert result.passed is False
        assert any("Search volume too low" in reason for reason in result.rejection_reasons)
        assert "300 < 350" in result.rejection_reasons[0]
        assert "region: UK" in result.rejection_reasons[0]

    def test_cn_region_uses_higher_threshold(self):
        """Test CN region uses 800 search volume threshold."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=900,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="CN",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_cn_region_rejects_below_threshold(self):
        """Test CN region rejects below 800 search volume."""
        result = DemandValidationResult(
            keyword="obscure product",
            search_volume=700,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="CN",
        )

        assert result.passed is False
        assert any("Search volume too low" in reason for reason in result.rejection_reasons)
        assert "700 < 800" in result.rejection_reasons[0]
        assert "region: CN" in result.rejection_reasons[0]

    def test_cn_region_rejects_medium_competition(self):
        """Test CN region rejects MEDIUM competition (stricter than US/EU)."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=5000,
            competition_density=CompetitionDensity.MEDIUM,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="CN",
        )

        assert result.passed is False
        assert any("Competition density too high" in reason for reason in result.rejection_reasons)
        assert "medium" in result.rejection_reasons[0]
        assert "max: low" in result.rejection_reasons[0]
        assert "region: CN" in result.rejection_reasons[0]

    def test_us_region_accepts_medium_competition(self):
        """Test US region accepts MEDIUM competition."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=5000,
            competition_density=CompetitionDensity.MEDIUM,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_us_region_rejects_high_competition(self):
        """Test US region rejects HIGH competition."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=5000,
            competition_density=CompetitionDensity.HIGH,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
        )

        assert result.passed is False
        assert any("Competition density too high" in reason for reason in result.rejection_reasons)
        assert "high" in result.rejection_reasons[0]
        assert "max: medium" in result.rejection_reasons[0]
        assert "region: US" in result.rejection_reasons[0]

    def test_unknown_region_uses_default_threshold(self):
        """Test unknown region falls back to US defaults."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=600,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="XX",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_none_region_uses_default_threshold(self):
        """Test None region falls back to US defaults."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=600,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region=None,
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0


class TestCategorySpecificValidation:
    """Test category-specific demand validation thresholds."""

    def test_electronics_uses_lower_threshold(self):
        """Test electronics category uses 0.5x multiplier (US 500 -> 250)."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=300,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="electronics",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_electronics_rejects_below_lowered_threshold(self):
        """Test electronics rejects below 250 (US 500 * 0.5)."""
        result = DemandValidationResult(
            keyword="obscure gadget",
            search_volume=200,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="electronics",
        )

        assert result.passed is False
        assert any("Search volume too low" in reason for reason in result.rejection_reasons)
        assert "200 < 250" in result.rejection_reasons[0]
        assert "category: electronics" in result.rejection_reasons[0]

    def test_jewelry_uses_higher_threshold(self):
        """Test jewelry category uses 1.5x multiplier (US 500 -> 750)."""
        result = DemandValidationResult(
            keyword="diamond ring",
            search_volume=800,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="jewelry",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_jewelry_rejects_below_raised_threshold(self):
        """Test jewelry rejects below 750 (US 500 * 1.5)."""
        result = DemandValidationResult(
            keyword="niche bracelet",
            search_volume=600,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="jewelry",
        )

        assert result.passed is False
        assert any("Search volume too low" in reason for reason in result.rejection_reasons)
        assert "600 < 750" in result.rejection_reasons[0]
        assert "category: jewelry" in result.rejection_reasons[0]

    def test_jewelry_rejects_medium_competition(self):
        """Test jewelry category rejects MEDIUM competition (stricter than general)."""
        result = DemandValidationResult(
            keyword="gold necklace",
            search_volume=5000,
            competition_density=CompetitionDensity.MEDIUM,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="jewelry",
        )

        assert result.passed is False
        assert any("Competition density too high" in reason for reason in result.rejection_reasons)
        assert "medium" in result.rejection_reasons[0]
        assert "max: low" in result.rejection_reasons[0]
        assert "category: jewelry" in result.rejection_reasons[0]

    def test_beauty_rejects_medium_competition(self):
        """Test beauty category rejects MEDIUM competition."""
        result = DemandValidationResult(
            keyword="face cream",
            search_volume=5000,
            competition_density=CompetitionDensity.MEDIUM,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="beauty",
        )

        assert result.passed is False
        assert any("Competition density too high" in reason for reason in result.rejection_reasons)

    def test_fashion_uses_moderate_threshold(self):
        """Test fashion category uses 0.7x multiplier (US 500 -> 350)."""
        result = DemandValidationResult(
            keyword="summer dress",
            search_volume=400,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="fashion",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_home_uses_moderate_threshold(self):
        """Test home category uses 0.8x multiplier (US 500 -> 400)."""
        result = DemandValidationResult(
            keyword="storage box",
            search_volume=450,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="home",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_category_and_region_combined(self):
        """Test category multiplier applies to region baseline (UK 350 * 0.5 = 175 for electronics)."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=200,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="UK",
            category="electronics",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_unknown_category_uses_baseline(self):
        """Test unknown category uses 1.0x multiplier (no adjustment)."""
        result = DemandValidationResult(
            keyword="random product",
            search_volume=600,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="unknown_category",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0


class TestPlatformSpecificValidation:
    """Test platform-specific demand validation thresholds."""

    def test_amazon_uses_higher_search_threshold(self):
        """Test Amazon uses 1.3x multiplier (US 500 -> 650)."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=700,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            platform="amazon",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_amazon_rejects_below_higher_threshold(self):
        """Test Amazon rejects below 650 (US 500 * 1.3)."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=600,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            platform="amazon",
        )

        assert result.passed is False
        assert any("Search volume too low" in reason for reason in result.rejection_reasons)
        assert "600 < 650" in result.rejection_reasons[0]
        assert "platform: amazon" in result.rejection_reasons[0]

    def test_amazon_rejects_medium_competition(self):
        """Test Amazon rejects MEDIUM competition."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=5000,
            competition_density=CompetitionDensity.MEDIUM,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            platform="amazon",
        )

        assert result.passed is False
        assert any("Competition density too high" in reason for reason in result.rejection_reasons)
        assert "medium" in result.rejection_reasons[0]
        assert "max: low" in result.rejection_reasons[0]
        assert "platform: amazon" in result.rejection_reasons[0]

    def test_temu_uses_lower_search_threshold(self):
        """Test Temu uses 0.9x multiplier (US 500 -> 450)."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=460,
            competition_density=CompetitionDensity.MEDIUM,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            platform="temu",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_temu_accepts_medium_competition(self):
        """Test Temu accepts MEDIUM competition."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=5000,
            competition_density=CompetitionDensity.MEDIUM,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            platform="temu",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_rakuten_rejects_medium_competition(self):
        """Test Rakuten rejects MEDIUM competition."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=5000,
            competition_density=CompetitionDensity.MEDIUM,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            platform="rakuten",
        )

        assert result.passed is False
        assert any("Competition density too high" in reason for reason in result.rejection_reasons)

    def test_platform_and_category_combined(self):
        """Test platform and category multipliers combine (US 500 * 0.5 * 1.3 = 325)."""
        result = DemandValidationResult(
            keyword="phone charger",
            search_volume=350,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="electronics",
            platform="amazon",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_platform_region_category_combined_stricter_competition(self):
        """Test combined rules choose strictest competition threshold."""
        result = DemandValidationResult(
            keyword="gold necklace",
            search_volume=5000,
            competition_density=CompetitionDensity.MEDIUM,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            category="jewelry",
            platform="temu",
        )

        assert result.passed is False
        assert any("Competition density too high" in reason for reason in result.rejection_reasons)
        assert "max: low" in result.rejection_reasons[0]

    def test_unknown_platform_uses_baseline(self):
        """Test unknown platform uses baseline thresholds."""
        result = DemandValidationResult(
            keyword="phone case",
            search_volume=600,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
            trend_growth_rate=Decimal("0.25"),
            region="US",
            platform="unknown_platform",
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0


class TestHelium10Integration:
    """Test Helium 10 integration within the current provider chain."""

    @pytest.mark.asyncio
    async def test_helium10_enabled_with_valid_key(self):
        """Test Helium 10 is used after AlphaShop returns no data."""
        validator = DemandValidator(
            use_helium10=True,
            helium10_api_key="test_api_key",
        )

        with patch.object(
            validator,
            "_get_trends_from_alphashop",
            new_callable=AsyncMock,
            return_value=(None, None, TrendDirection.UNKNOWN),
        ) as mock_alpha:
            with patch("app.clients.helium10.Helium10Client") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.get_keyword_data.return_value = {
                    "search_volume": 3000,
                    "competition_score": 45,
                    "trend_direction": "rising",
                    "trend_growth_rate": 0.30,
                }
                mock_client_instance.close = AsyncMock()
                MockClient.return_value = mock_client_instance

                with patch.object(
                    validator,
                    "_assess_competition_density",
                    return_value=CompetitionDensity.MEDIUM,
                ):
                    result = await validator.validate(
                        keyword="phone case",
                        category="electronics",
                        region="US",
                    )

        assert result.search_volume == 3000
        assert result.trend_direction == TrendDirection.RISING
        assert result.trend_growth_rate == Decimal("0.30")
        assert result.passed is True
        mock_alpha.assert_called_once()
        mock_client_instance.get_keyword_data.assert_called_once_with(
            keyword="phone case",
            marketplace="US",
        )
        mock_client_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_helium10_fallback_to_legacy_provider_on_error(self):
        """Test fallback to legacy provider when Helium 10 returns no data."""
        validator = DemandValidator(
            use_helium10=True,
            helium10_api_key="test_api_key",
        )

        with patch.object(
            validator,
            "_get_trends_from_alphashop",
            new_callable=AsyncMock,
            return_value=(None, None, TrendDirection.UNKNOWN),
        ):
            with patch("app.clients.helium10.Helium10Client") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.get_keyword_data.return_value = None
                mock_client_instance.close = AsyncMock()
                MockClient.return_value = mock_client_instance

                with patch.object(
                    validator,
                    "_get_trends_from_pytrends",
                    return_value=(2000, Decimal("0.25"), TrendDirection.RISING),
                ):
                    with patch.object(
                        validator,
                        "_assess_competition_density",
                        return_value=CompetitionDensity.LOW,
                    ):
                        result = await validator.validate(
                            keyword="phone case",
                            category="electronics",
                            region="US",
                        )

        assert result.search_volume == 2000
        assert result.trend_direction == TrendDirection.RISING
        assert result.trend_growth_rate == Decimal("0.25")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_helium10_fallback_to_legacy_provider_on_exception(self):
        """Test fallback to legacy provider when Helium 10 raises exception."""
        validator = DemandValidator(
            use_helium10=True,
            helium10_api_key="test_api_key",
        )

        with patch.object(
            validator,
            "_get_trends_from_alphashop",
            new_callable=AsyncMock,
            return_value=(None, None, TrendDirection.UNKNOWN),
        ):
            with patch("app.clients.helium10.Helium10Client") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.get_keyword_data.side_effect = Exception("API error")
                mock_client_instance.close = AsyncMock()
                MockClient.return_value = mock_client_instance

                with patch.object(
                    validator,
                    "_get_trends_from_pytrends",
                    return_value=(2000, Decimal("0.25"), TrendDirection.RISING),
                ):
                    with patch.object(
                        validator,
                        "_assess_competition_density",
                        return_value=CompetitionDensity.LOW,
                    ):
                        result = await validator.validate(
                            keyword="phone case",
                            category="electronics",
                            region="US",
                        )

        assert result.search_volume == 2000
        assert result.trend_direction == TrendDirection.RISING
        assert result.trend_growth_rate == Decimal("0.25")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_helium10_disabled_uses_legacy_fallback_when_alphashop_unavailable(self):
        """Test legacy fallback is used when Helium 10 is disabled and AlphaShop has no data."""
        validator = DemandValidator(
            use_helium10=False,
        )

        with patch.object(
            validator,
            "_get_trends_from_alphashop",
            new_callable=AsyncMock,
            return_value=(None, None, TrendDirection.UNKNOWN),
        ) as mock_alpha:
            with patch.object(
                validator,
                "_get_trends_from_pytrends",
                return_value=(2000, Decimal("0.25"), TrendDirection.RISING),
            ) as mock_pytrends:
                with patch.object(
                    validator,
                    "_assess_competition_density",
                    return_value=CompetitionDensity.LOW,
                ):
                    result = await validator.validate(
                        keyword="phone case",
                        category="electronics",
                        region="US",
                    )

        assert result.search_volume == 2000
        assert result.trend_direction == TrendDirection.RISING
        assert result.passed is True
        mock_alpha.assert_called_once()
        mock_pytrends.assert_called_once()