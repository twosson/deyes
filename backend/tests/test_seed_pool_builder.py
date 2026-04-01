"""Tests for seed pool builder service."""
import pytest
from unittest.mock import MagicMock

from app.services.seed_pool_builder import Seed, SeedPoolBuilderService


class TestSeed:
    """Test Seed dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        seed = Seed(
            term="wireless charger",
            source="user",
            confidence=1.0,
            category="electronics",
            region="US",
            platform="amazon",
        )

        seed_dict = seed.to_dict()

        assert seed_dict["term"] == "wireless charger"
        assert seed_dict["source"] == "user"
        assert seed_dict["confidence"] == 1.0
        assert seed_dict["category"] == "electronics"
        assert seed_dict["region"] == "US"
        assert seed_dict["platform"] == "amazon"


class TestSeedPoolBuilderService:
    """Test SeedPoolBuilderService."""

    @pytest.mark.asyncio
    async def test_build_seed_pool_with_user_keywords(self):
        """Test seed pool building with user keywords."""
        service = SeedPoolBuilderService()

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=["wireless charger", "phone case"],
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        assert len(seeds) >= 2
        assert seeds[0].term == "wireless charger"
        assert seeds[0].source == "user"
        assert seeds[0].confidence == 1.0
        assert seeds[1].term == "phone case"
        assert seeds[1].source == "user"

    @pytest.mark.asyncio
    async def test_build_seed_pool_with_category_static(self):
        """Test seed pool building with category static seeds."""
        service = SeedPoolBuilderService()

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        assert len(seeds) > 0
        assert all(seed.source == "category_static" for seed in seeds)
        assert all(seed.category == "electronics" for seed in seeds)

    @pytest.mark.asyncio
    async def test_build_seed_pool_deduplicates(self):
        """Test seed pool deduplicates keywords."""
        service = SeedPoolBuilderService()

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=["phone case", "Phone Case", "  phone case  "],
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        # Should only have one "phone case" seed
        phone_case_seeds = [s for s in seeds if s.term.lower().strip() == "phone case"]
        assert len(phone_case_seeds) == 1

    @pytest.mark.asyncio
    async def test_build_seed_pool_respects_max_seeds(self):
        """Test seed pool respects max_seeds limit."""
        service = SeedPoolBuilderService()

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=3,
        )

        assert len(seeds) <= 3

    @pytest.mark.asyncio
    async def test_build_seed_pool_with_historical_feedback(self):
        """Test seed pool includes historical feedback when available."""
        mock_feedback = MagicMock()
        mock_feedback.get_high_performing_seeds.return_value = [
            "trending product 1",
            "trending product 2",
        ]

        service = SeedPoolBuilderService(feedback_aggregator=mock_feedback)

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        historical_seeds = [s for s in seeds if s.source == "historical"]
        assert len(historical_seeds) == 2
        assert historical_seeds[0].term == "trending product 1"
        assert historical_seeds[1].term == "trending product 2"

    @pytest.mark.asyncio
    async def test_build_seed_pool_unknown_category(self):
        """Test seed pool with unknown category returns empty list."""
        service = SeedPoolBuilderService()

        seeds = await service.build_seed_pool(
            category="unknown_category",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        assert len(seeds) == 0
