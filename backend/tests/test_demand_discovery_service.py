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
def mock_seed_fallback_provider():
    """Mock seed fallback provider."""
    provider = AsyncMock()
    provider.get_candidate_fallback_keywords = AsyncMock()
    return provider


@pytest.fixture
def demand_discovery_service(
    mock_demand_validator,
    mock_keyword_generator,
    mock_seed_fallback_provider,
):
    """Create demand discovery service with mocks."""
    return DemandDiscoveryService(
        demand_validator=mock_demand_validator,
        keyword_generator=mock_keyword_generator,
        seed_fallback_provider=mock_seed_fallback_provider,
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
    async def test_generation_fails_triggers_fallback(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_keyword_generator,
        mock_seed_fallback_provider,
    ):
        """Test generation failure triggers fallback seeds."""
        # Arrange
        mock_keyword_generator.generate_selection_keywords.side_effect = Exception(
            "API error"
        )

        mock_seed_fallback_provider.get_candidate_fallback_keywords.return_value = [
            ("热销", "seasonal"),
            ("新品", "cold_start"),
        ]

        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword="热销",
                search_volume=3000,
                competition_density=CompetitionDensity.MEDIUM,
                trend_direction=TrendDirection.STABLE,
                trend_growth_rate=None,
                passed=True,
            ),
            DemandValidationResult(
                keyword="新品",
                search_volume=2500,
                competition_density=CompetitionDensity.MEDIUM,
                trend_direction=TrendDirection.STABLE,
                trend_growth_rate=None,
                passed=True,
            ),
        ]

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=None,
            region="US",
            allow_fallback=True,
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "fallback"
        assert len(result.validated_keywords) == 2
        assert result.validated_keywords[0].source == "fallback_seasonal"
        assert result.validated_keywords[1].source == "fallback_cold_start"
        assert result.fallback_used is True
        assert result.degraded is True

    @pytest.mark.asyncio
    async def test_all_paths_fail_returns_empty(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_keyword_generator,
        mock_seed_fallback_provider,
    ):
        """Test all discovery paths fail returns empty result."""
        # Arrange
        mock_keyword_generator.generate_selection_keywords.return_value = []
        mock_seed_fallback_provider.get_candidate_fallback_keywords.return_value = []

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=None,
            region="US",
            allow_fallback=True,
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "fallback"
        assert len(result.validated_keywords) == 0
        assert result.fallback_used is True
        assert result.degraded is True

    @pytest.mark.asyncio
    async def test_fallback_disabled_skips_fallback(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_keyword_generator,
        mock_seed_fallback_provider,
    ):
        """Test fallback disabled skips fallback seeds."""
        # Arrange
        mock_keyword_generator.generate_selection_keywords.return_value = []

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=None,
            region="US",
            allow_fallback=False,
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "none"
        assert len(result.validated_keywords) == 0
        assert result.fallback_used is False
        assert result.degraded is True
        mock_seed_fallback_provider.get_candidate_fallback_keywords.assert_not_called()

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
    async def test_max_keywords_limit_enforced(
        self,
        demand_discovery_service,
        mock_demand_validator,
    ):
        """Test max_keywords limit is enforced."""
        # Arrange
        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword=f"keyword{i}",
                search_volume=5000,
                competition_density=CompetitionDensity.LOW,
                trend_direction=TrendDirection.RISING,
                trend_growth_rate=None,
                passed=True,
            )
            for i in range(20)
        ]

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=[f"keyword{i}" for i in range(20)],
            region="US",
            max_keywords=5,
        )

        # Assert
        assert len(result.validated_keywords) == 5
