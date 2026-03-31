"""Tests for DemandDiscoveryService."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.demand_discovery_service import (
    DemandDiscoveryKeyword,
    DemandDiscoveryResult,
    DemandDiscoveryService,
)
from app.services.demand_validator import (
    CompetitionDensity,
    DemandValidationResult,
    TrendDirection,
)
from app.services.keyword_generator import KeywordResult


@pytest.fixture
def mock_demand_validator():
    """Mock demand validator."""
    validator = AsyncMock()
    validator.validate_batch = AsyncMock()
    return validator


@pytest.fixture
def mock_keyword_generator():
    """Mock keyword generator."""
    generator = AsyncMock()
    generator.generate_selection_keywords = AsyncMock()
    return generator


@pytest.fixture
def demand_discovery_service(
    mock_demand_validator,
    mock_keyword_generator,
):
    """Create demand discovery service with mocks."""
    return DemandDiscoveryService(
        demand_validator=mock_demand_validator,
        keyword_generator=mock_keyword_generator,
    )


class TestDemandDiscoveryService:
    """Test DemandDiscoveryService."""

    @pytest.mark.asyncio
    async def test_user_keywords_validated_success(
        self,
        demand_discovery_service,
        mock_demand_validator,
    ):
        """Test user keywords validated successfully."""
        # Arrange
        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword="wireless earbuds",
                search_volume=5000,
                competition_density=CompetitionDensity.LOW,
                trend_direction=TrendDirection.RISING,
                trend_growth_rate=None,
                passed=True,
            ),
        ]

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=["wireless earbuds"],
            region="US",
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "user"
        assert len(result.validated_keywords) == 1
        assert result.validated_keywords[0].keyword == "wireless earbuds"
        assert result.validated_keywords[0].source == "user"
        assert result.fallback_used is False
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_user_keywords_all_rejected_triggers_generation(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_keyword_generator,
    ):
        """Test user keywords rejected triggers keyword generation."""
        # Arrange
        mock_demand_validator.validate_batch.side_effect = [
            # User keywords rejected
            [
                DemandValidationResult(
                    keyword="bad keyword",
                    search_volume=10,
                    competition_density=CompetitionDensity.HIGH,
                    trend_direction=TrendDirection.DECLINING,
                    trend_growth_rate=None,
                    passed=False,
                    rejection_reasons=["low_search_volume"],
                ),
            ],
            # Generated keywords validated
            [
                DemandValidationResult(
                    keyword="trending product",
                    search_volume=8000,
                    competition_density=CompetitionDensity.LOW,
                    trend_direction=TrendDirection.RISING,
                    trend_growth_rate=None,
                    passed=True,
                ),
            ],
        ]

        mock_keyword_generator.generate_selection_keywords.return_value = [
            KeywordResult(
                keyword="trending product",
                search_volume=8000,
                trend_score=85,
                competition_density=CompetitionDensity.LOW,
                related_keywords=[],
                category="electronics",
                region="US",
            ),
        ]

        demand_discovery_service.logger = MagicMock()

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=["bad keyword"],
            region="US",
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "generated"
        assert len(result.validated_keywords) == 1
        assert result.validated_keywords[0].keyword == "trending product"
        assert result.validated_keywords[0].source == "generated"
        assert len(result.rejected_keywords) == 1
        assert result.rejected_keywords[0].keyword == "bad keyword"
        assert result.fallback_used is False
        assert result.degraded is True  # User keywords failed
        demand_discovery_service.logger.info.assert_any_call(
            "demand_discovery_metrics",
            category="electronics",
            region="US",
            platform=None,
            discovery_mode="generated",
            success=True,
            skip=False,
            fallback_used=False,
            degraded=True,
            generated_recovery=True,
            validated_fallback=False,
            validated_keywords_count=1,
            rejected_keywords_count=1,
            avg_validated_keywords_count=1,
            discovery_success_rate=1.0,
            generated_recovery_rate=1.0,
            validated_fallback_rate=0.0,
            skip_rate=0.0,
            selection_triggered_per_category=1,
        )

    @pytest.mark.asyncio
    async def test_no_user_keywords_triggers_generation(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_keyword_generator,
    ):
        """Test no user keywords triggers keyword generation."""
        # Arrange
        mock_keyword_generator.generate_selection_keywords.return_value = [
            KeywordResult(
                keyword="smart watch",
                search_volume=12000,
                trend_score=90,
                competition_density=CompetitionDensity.MEDIUM,
                related_keywords=["fitness tracker"],
                category="electronics",
                region="US",
            ),
        ]

        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword="smart watch",
                search_volume=12000,
                competition_density=CompetitionDensity.MEDIUM,
                trend_direction=TrendDirection.RISING,
                trend_growth_rate=None,
                passed=True,
            ),
        ]

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=None,
            region="US",
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "generated"
        assert len(result.validated_keywords) == 1
        assert result.validated_keywords[0].keyword == "smart watch"
        assert result.fallback_used is False
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_generation_fails_returns_empty(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_keyword_generator,
    ):
        """Test generation failure returns empty result with degraded flag."""
        # Arrange
        mock_keyword_generator.generate_selection_keywords.side_effect = Exception(
            "API error"
        )

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=None,
            region="US",
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "generated"
        assert len(result.validated_keywords) == 0
        assert result.fallback_used is False
        assert result.degraded is True

    @pytest.mark.asyncio
    async def test_all_paths_fail_returns_empty(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_keyword_generator,
    ):
        """Test all discovery paths fail returns empty result."""
        # Arrange
        mock_keyword_generator.generate_selection_keywords.return_value = []

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=None,
            region="US",
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "none"
        assert len(result.validated_keywords) == 0
        assert result.fallback_used is False
        assert result.degraded is True

    @pytest.mark.asyncio
    async def test_generation_empty_returns_none_mode(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_keyword_generator,
    ):
        """Test generation returning empty list results in none mode."""
        # Arrange
        mock_keyword_generator.generate_selection_keywords.return_value = []

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=None,
            region="US",
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "none"
        assert len(result.validated_keywords) == 0
        assert result.fallback_used is False
        assert result.degraded is True

    @pytest.mark.asyncio
    async def test_keyword_normalization_deduplicates(
        self,
        demand_discovery_service,
        mock_demand_validator,
    ):
        """Test keyword normalization removes duplicates."""
        # Arrange
        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword="bluetooth speaker",
                search_volume=6000,
                competition_density=CompetitionDensity.LOW,
                trend_direction=TrendDirection.RISING,
                trend_growth_rate=None,
                passed=True,
            ),
        ]

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=["bluetooth speaker", "  bluetooth speaker  ", "bluetooth speaker"],
            region="US",
            max_keywords=10,
        )

        # Assert
        assert len(result.validated_keywords) == 1
        mock_demand_validator.validate_batch.assert_called_once()
        call_args = mock_demand_validator.validate_batch.call_args
        assert len(call_args.kwargs["keywords"]) == 1

    @pytest.mark.asyncio
    async def test_region_passed_to_validator_and_generator(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_keyword_generator,
    ):
        """Test region is propagated to generator and validator for runtime discovery."""
        mock_keyword_generator.generate_selection_keywords.return_value = [
            KeywordResult(
                keyword="smart watch",
                search_volume=12000,
                trend_score=90,
                competition_density=CompetitionDensity.MEDIUM,
                related_keywords=["fitness tracker"],
                category="electronics",
                region="DE",
            ),
        ]

        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword="smart watch",
                search_volume=12000,
                competition_density=CompetitionDensity.MEDIUM,
                trend_direction=TrendDirection.RISING,
                trend_growth_rate=None,
                passed=True,
                region="DE",
            ),
        ]

        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=None,
            region="DE",
            max_keywords=10,
        )

        assert result.discovery_mode == "generated"
        mock_keyword_generator.generate_selection_keywords.assert_called_once_with(
            category="electronics",
            region="DE",
            limit=20,
            expand_top_n=5,
        )
        mock_demand_validator.validate_batch.assert_called_once_with(
            keywords=["smart watch"],
            category="electronics",
            region="DE",
            platform=None,
        )

    @pytest.mark.asyncio
    async def test_platform_passed_to_validator(
        self,
        demand_discovery_service,
        mock_demand_validator,
    ):
        """Test platform is propagated to validator."""
        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword="wireless earbuds",
                search_volume=5000,
                competition_density=CompetitionDensity.LOW,
                trend_direction=TrendDirection.RISING,
                trend_growth_rate=None,
                passed=True,
                platform="amazon",
            ),
        ]

        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=["wireless earbuds"],
            region="US",
            platform="amazon",
            max_keywords=10,
        )

        assert result.discovery_mode == "user"
        mock_demand_validator.validate_batch.assert_called_once_with(
            keywords=["wireless earbuds"],
            category="electronics",
            region="US",
            platform="amazon",
        )

    @pytest.mark.asyncio
    async def test_default_region_used_when_region_missing(
        self,
        demand_discovery_service,
        mock_demand_validator,
    ):
        """Test default US region is used when region is missing."""
        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword="wireless earbuds",
                search_volume=5000,
                competition_density=CompetitionDensity.LOW,
                trend_direction=TrendDirection.RISING,
                trend_growth_rate=None,
                passed=True,
                region="US",
            ),
        ]

        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=["wireless earbuds"],
            region=None,
            max_keywords=10,
        )

        assert result.discovery_mode == "user"
        mock_demand_validator.validate_batch.assert_called_once_with(
            keywords=["wireless earbuds"],
            category="electronics",
            region="US",
            platform=None,
        )
