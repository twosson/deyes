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
from app.services.exploration_seed_provider import ExplorationSeed
from app.services.keyword_legitimizer import ValidKeyword
from app.services.seed_pool_builder import Seed


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
def mock_keyword_legitimizer():
    """Mock keyword legitimizer that converts seeds to valid keywords."""
    legitimizer = AsyncMock()

    async def legitimize_side_effect(*, seeds, region, platform):
        results = []
        for seed in seeds:
            results.append(
                ValidKeyword(
                    seed=seed,
                    matched_keyword=seed.term,
                    match_type="exact",
                    opp_score=50.0,
                    search_volume=5000,
                    competition_density="low",
                    is_valid_for_report=True,
                    raw={"keyword": seed.term},
                    report_keyword=seed.term,
                )
            )
        return results

    legitimizer.legitimize_seeds.side_effect = legitimize_side_effect
    return legitimizer


@pytest.fixture
def mock_seed_pool_builder():
    """Mock seed pool builder that returns empty list by default."""
    builder = AsyncMock()
    builder.build_seed_pool.return_value = []
    return builder


@pytest.fixture
def mock_exploration_seed_provider():
    """Mock exploration seed provider that returns empty list by default."""
    provider = AsyncMock()
    provider.get_exploration_seeds.return_value = []
    return provider


@pytest.fixture
def demand_discovery_service(
    mock_demand_validator,
    mock_keyword_generator,
    mock_keyword_legitimizer,
    mock_seed_pool_builder,
    mock_exploration_seed_provider,
):
    """Create demand discovery service with mocks."""
    return DemandDiscoveryService(
        demand_validator=mock_demand_validator,
        keyword_generator=mock_keyword_generator,
        keyword_legitimizer=mock_keyword_legitimizer,
        seed_pool_builder=mock_seed_pool_builder,
        exploration_seed_provider=mock_exploration_seed_provider,
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
    async def test_user_keywords_all_rejected_returns_none_without_generated_recovery(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_seed_pool_builder,
    ):
        """Rejected user keywords should not trigger fallback recovery."""
        # Arrange
        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword="bad keyword",
                search_volume=10,
                competition_density=CompetitionDensity.HIGH,
                trend_direction=TrendDirection.DECLINING,
                trend_growth_rate=None,
                passed=False,
                rejection_reasons=["low_search_volume"],
            ),
        ]
        mock_seed_pool_builder.build_seed_pool.return_value = []

        demand_discovery_service.logger = MagicMock()

        # Act
        result = await demand_discovery_service.discover_keywords(
            category="electronics",
            keywords=["bad keyword"],
            region="US",
            max_keywords=10,
        )

        # Assert
        assert result.discovery_mode == "none"
        assert len(result.validated_keywords) == 0
        assert len(result.rejected_keywords) == 1
        assert result.rejected_keywords[0].keyword == "bad keyword"
        assert result.rejected_keywords[0].source == "user"
        assert result.fallback_used is False
        assert result.degraded is True
        demand_discovery_service.logger.info.assert_any_call(
            "demand_discovery_metrics",
            category="electronics",
            region="US",
            platform=None,
            discovery_mode="none",
            success=False,
            skip=True,
            fallback_used=False,
            degraded=True,
            generated_recovery=False,
            validated_fallback=False,
            validated_keywords_count=0,
            rejected_keywords_count=1,
            avg_validated_keywords_count=0,
            discovery_success_rate=0.0,
            generated_recovery_rate=0.0,
            validated_fallback_rate=0.0,
            skip_rate=1.0,
            selection_triggered_per_category=0,
        )

    @pytest.mark.asyncio
    async def test_no_user_keywords_uses_seed_pool(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_seed_pool_builder,
    ):
        """Test no user keywords triggers category seed-pool discovery."""
        # Arrange
        mock_seed_pool_builder.build_seed_pool.return_value = [
            Seed(
                term="smart watch",
                source="category_static",
                confidence=0.5,
                category="electronics",
                region="US",
                platform=None,
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
        assert result.discovery_mode == "seed_pool"
        assert len(result.validated_keywords) == 1
        assert result.validated_keywords[0].keyword == "smart watch"
        assert result.fallback_used is False
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_empty_seed_pool_returns_empty(
        self,
        demand_discovery_service,
        mock_seed_pool_builder,
    ):
        """Test empty seed pool returns empty result with degraded flag."""
        # Arrange
        mock_seed_pool_builder.build_seed_pool.return_value = []

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
    async def test_all_paths_fail_returns_empty(
        self,
        demand_discovery_service,
        mock_seed_pool_builder,
    ):
        """Test user path and seed-pool path both failing returns empty result."""
        # Arrange
        mock_seed_pool_builder.build_seed_pool.return_value = []

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
    async def test_seed_pool_empty_returns_none_mode(
        self,
        demand_discovery_service,
        mock_seed_pool_builder,
    ):
        """Test seed-pool returning empty list results in none mode."""
        # Arrange
        mock_seed_pool_builder.build_seed_pool.return_value = []

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
    async def test_region_passed_to_seed_pool_and_validator(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_seed_pool_builder,
    ):
        """Test region is propagated to seed pool builder and validator for category discovery."""
        mock_seed_pool_builder.build_seed_pool.return_value = [
            Seed(
                term="smart watch",
                source="category_static",
                confidence=0.5,
                category="electronics",
                region="DE",
                platform=None,
            )
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

        assert result.discovery_mode == "seed_pool"
        mock_seed_pool_builder.build_seed_pool.assert_called_once_with(
            category="electronics",
            user_keywords=None,
            region="DE",
            platform=None,
            max_seeds=20,
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

    @pytest.mark.asyncio
    async def test_exploration_mode_discovers_keywords_without_inputs(
        self,
        demand_discovery_service,
        mock_demand_validator,
        mock_exploration_seed_provider,
    ):
        """No category/keywords should enter exploration mode and validate discovered keywords."""
        mock_exploration_seed_provider.get_exploration_seeds.return_value = [
            ExplorationSeed(
                term="phone accessories",
                source="supply",
                confidence=0.4,
                metadata={"signal_type": "supply", "region": "US"},
            )
        ]
        mock_demand_validator.validate_batch.return_value = [
            DemandValidationResult(
                keyword="phone accessories",
                search_volume=5000,
                competition_density=CompetitionDensity.MEDIUM,
                trend_direction=TrendDirection.RISING,
                trend_growth_rate=None,
                passed=True,
                region="US",
            ),
        ]

        result = await demand_discovery_service.discover_keywords(
            category=None,
            keywords=None,
            region="US",
            max_keywords=10,
        )

        assert result.discovery_mode == "exploration"
        assert len(result.validated_keywords) == 1
        assert result.validated_keywords[0].keyword == "phone accessories"
        assert result.validated_keywords[0].source == "supply"
        assert result.fallback_used is False
        assert result.degraded is False
        assert result.seeds[0]["term"] == "phone accessories"

    @pytest.mark.asyncio
    async def test_exploration_mode_returns_degraded_when_no_seeds(
        self,
        demand_discovery_service,
        mock_exploration_seed_provider,
    ):
        """Exploration mode should return degraded result when no exploration seeds are available."""
        mock_exploration_seed_provider.get_exploration_seeds.return_value = []

        result = await demand_discovery_service.discover_keywords(
            category=None,
            keywords=None,
            region="US",
            max_keywords=10,
        )

        assert result.discovery_mode == "exploration"
        assert result.validated_keywords == []
        assert result.degraded is True
        assert result.degraded_reason == "no_exploration_seeds_available"
