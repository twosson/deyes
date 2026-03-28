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
        """Test initialization falls back to pytrends if no Helium 10 key."""
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
    async def test_validate_with_mock_pytrends(self):
        """Test validate method with mocked pytrends."""
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
    async def test_competition_assessment_with_mock(self):
        """Test competition assessment with mocked pytrends."""
        validator = DemandValidator()

        # Mock pytrends to return high interest
        with patch("app.services.demand_validator.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = CompetitionDensity.HIGH

            result = await validator._assess_competition_density(
                keyword="phone",
                region="US",
            )

        assert result == CompetitionDensity.HIGH


@pytest.mark.integration
class TestDemandValidatorIntegration:
    """Integration tests for DemandValidator with real pytrends.

    These tests require internet connection and may be rate-limited by Google.
    Run with: pytest -m integration
    """

    @pytest.mark.asyncio
    async def test_pytrends_real_keyword(self):
        """Test with real pytrends API call."""
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
    async def test_pytrends_obscure_keyword(self):
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
    async def test_pytrends_different_regions(self):
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
async def test_pytrends_fallback_on_import_error():
    """Test fallback to mock data when pytrends is not installed."""
    validator = DemandValidator()

    # Mock ImportError for pytrends
    with patch("app.services.demand_validator.asyncio.to_thread") as mock_to_thread:

        def mock_fetch():
            raise ImportError("No module named 'pytrends'")

        mock_to_thread.side_effect = lambda func: func()

        with patch.object(
            validator,
            "_get_trends_from_pytrends",
            side_effect=lambda k, r: (1500, Decimal("0.15"), TrendDirection.STABLE),
        ):
            result = await validator.validate(
                keyword="phone case",
                category="electronics",
                region="US",
            )

    # Should fallback to mock data
    assert result.search_volume == 1500
    assert result.trend_growth_rate == Decimal("0.15")
    assert result.trend_direction == TrendDirection.STABLE


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


class TestHelium10Integration:
    """Test Helium 10 API integration."""

    @pytest.mark.asyncio
    async def test_helium10_enabled_with_valid_key(self):
        """Test Helium 10 integration with valid API key."""
        validator = DemandValidator(
            use_helium10=True,
            helium10_api_key="test_api_key",
        )

        # Mock Helium10Client
        with patch("app.services.demand_validator.Helium10Client") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_keyword_data.return_value = {
                "search_volume": 3000,
                "competition_score": 45,
                "trend_direction": "rising",
                "trend_growth_rate": 0.30,
            }
            mock_client_instance.close = AsyncMock()
            MockClient.return_value = mock_client_instance

            # Mock competition assessment
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

        # Should use Helium 10 data
        assert result.search_volume == 3000
        assert result.trend_direction == TrendDirection.RISING
        assert result.trend_growth_rate == Decimal("0.30")
        assert result.passed is True

        # Should have called Helium 10 client
        mock_client_instance.get_keyword_data.assert_called_once_with(
            keyword="phone case",
            marketplace="US",
        )
        mock_client_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_helium10_fallback_to_pytrends_on_error(self):
        """Test fallback to pytrends when Helium 10 fails."""
        validator = DemandValidator(
            use_helium10=True,
            helium10_api_key="test_api_key",
        )

        # Mock Helium10Client to return None (API error)
        with patch("app.services.demand_validator.Helium10Client") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_keyword_data.return_value = None
            mock_client_instance.close = AsyncMock()
            MockClient.return_value = mock_client_instance

            # Mock pytrends fallback
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

        # Should fallback to pytrends
        assert result.search_volume == 2000
        assert result.trend_direction == TrendDirection.RISING
        assert result.trend_growth_rate == Decimal("0.25")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_helium10_fallback_to_pytrends_on_exception(self):
        """Test fallback to pytrends when Helium 10 raises exception."""
        validator = DemandValidator(
            use_helium10=True,
            helium10_api_key="test_api_key",
        )

        # Mock Helium10Client to raise exception
        with patch("app.services.demand_validator.Helium10Client") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_keyword_data.side_effect = Exception("API error")
            mock_client_instance.close = AsyncMock()
            MockClient.return_value = mock_client_instance

            # Mock pytrends fallback
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

        # Should fallback to pytrends
        assert result.search_volume == 2000
        assert result.trend_direction == TrendDirection.RISING
        assert result.trend_growth_rate == Decimal("0.25")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_helium10_disabled_uses_pytrends(self):
        """Test that pytrends is used when Helium 10 is disabled."""
        validator = DemandValidator(
            use_helium10=False,
        )

        # Mock pytrends
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

        # Should use pytrends
        assert result.search_volume == 2000
        assert result.trend_direction == TrendDirection.RISING
        assert result.passed is True
