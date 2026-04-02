"""Tests for seed pool builder service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.seed_pool_builder import Seed, SeedPoolBuilderService
from app.services.keyword_generator import KeywordResult


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
    async def test_build_seed_pool_with_alphashop_trending(self):
        """Test seed pool building with AlphaShop trending seeds."""
        mock_generator = AsyncMock()
        mock_generator.generate_selection_keywords = AsyncMock(
            return_value=[
                KeywordResult(
                    keyword="wireless earbuds",
                    search_volume=5000,
                    trend_score=85,
                    competition_density="medium",
                    category="electronics",
                    region="US",
                ),
                KeywordResult(
                    keyword="phone stand",
                    search_volume=3000,
                    trend_score=75,
                    competition_density="low",
                    category="electronics",
                    region="US",
                ),
            ]
        )

        service = SeedPoolBuilderService(keyword_generator=mock_generator)

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        alphashop_seeds = [s for s in seeds if s.source == "alphashop_trending"]
        assert len(alphashop_seeds) == 2
        assert alphashop_seeds[0].term == "wireless earbuds"
        assert alphashop_seeds[0].confidence == 0.75
        assert alphashop_seeds[1].term == "phone stand"

    @pytest.mark.asyncio
    async def test_build_seed_pool_with_category_static_fallback(self):
        """Test seed pool falls back to category static seeds when AlphaShop fails."""
        mock_generator = AsyncMock()
        mock_generator.generate_selection_keywords = AsyncMock(
            side_effect=Exception("AlphaShop unavailable")
        )

        service = SeedPoolBuilderService(keyword_generator=mock_generator)

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        # Should fall back to static seeds
        assert len(seeds) > 0
        assert all(seed.source == "category_static" for seed in seeds)
        assert all(seed.category == "electronics" for seed in seeds)

    @pytest.mark.asyncio
    async def test_build_seed_pool_no_static_when_alphashop_succeeds(self):
        """Test seed pool does not use static seeds when AlphaShop succeeds."""
        mock_generator = AsyncMock()
        mock_generator.generate_selection_keywords = AsyncMock(
            return_value=[
                KeywordResult(
                    keyword="trending product",
                    search_volume=5000,
                    trend_score=85,
                    competition_density="medium",
                    category="electronics",
                    region="US",
                ),
            ]
        )

        service = SeedPoolBuilderService(keyword_generator=mock_generator)

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        # Should NOT have static seeds when AlphaShop succeeds
        static_seeds = [s for s in seeds if s.source == "category_static"]
        assert len(static_seeds) == 0

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
    async def test_build_seed_pool_source_priority(self):
        """Test seed pool respects source priority ordering."""
        mock_feedback = MagicMock()
        mock_feedback.get_high_performing_seeds.return_value = ["historical keyword"]

        mock_generator = AsyncMock()
        mock_generator.generate_selection_keywords = AsyncMock(
            return_value=[
                KeywordResult(
                    keyword="alphashop keyword",
                    search_volume=5000,
                    trend_score=85,
                    competition_density="medium",
                    category="electronics",
                    region="US",
                ),
            ]
        )

        service = SeedPoolBuilderService(
            feedback_aggregator=mock_feedback,
            keyword_generator=mock_generator,
        )

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=["user keyword"],
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        # Check priority: user (1.0) > historical (0.8) > alphashop (0.75)
        assert seeds[0].source == "user"
        assert seeds[0].confidence == 1.0
        assert seeds[1].source == "historical"
        assert seeds[1].confidence == 0.8
        assert seeds[2].source == "alphashop_trending"
        assert seeds[2].confidence == 0.75

    @pytest.mark.asyncio
    async def test_build_seed_pool_unknown_category_with_alphashop(self):
        """Test seed pool with unknown category still tries AlphaShop."""
        mock_generator = AsyncMock()
        mock_generator.generate_selection_keywords = AsyncMock(
            return_value=[
                KeywordResult(
                    keyword="generic product",
                    search_volume=1000,
                    trend_score=50,
                    competition_density="high",
                    category="unknown_category",
                    region="US",
                ),
            ]
        )

        service = SeedPoolBuilderService(keyword_generator=mock_generator)

        seeds = await service.build_seed_pool(
            category="unknown_category",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        # Should have AlphaShop seeds even for unknown category
        assert len(seeds) > 0
        assert seeds[0].source == "alphashop_trending"

    @pytest.mark.asyncio
    async def test_build_seed_pool_with_seasonal_llm_expansion(self):
        """Test seed pool with seasonal LLM expansion."""
        mock_expander = AsyncMock()
        mock_expander.expand = AsyncMock(
            return_value=["wireless earbuds for dad", "desk gadget gift", "portable power bank"]
        )

        service = SeedPoolBuilderService(seasonal_seed_expander=mock_expander)

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        seasonal_llm_seeds = [s for s in seeds if s.source == "seasonal_llm"]
        assert len(seasonal_llm_seeds) > 0
        assert seasonal_llm_seeds[0].confidence == 0.72

    @pytest.mark.asyncio
    async def test_build_seed_pool_seasonal_llm_fallback(self):
        """Test seed pool falls back to template when LLM returns empty."""
        mock_expander = AsyncMock()
        mock_expander.expand = AsyncMock(return_value=[])  # Empty result

        service = SeedPoolBuilderService(seasonal_seed_expander=mock_expander)

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        seasonal_seeds = [s for s in seeds if s.source == "seasonal"]
        assert len(seasonal_seeds) > 0
        assert seasonal_seeds[0].confidence == 0.7

    @pytest.mark.asyncio
    async def test_build_seed_pool_seasonal_llm_exception_fallback(self):
        """Test seed pool falls back to template when LLM raises exception."""
        mock_expander = AsyncMock()
        mock_expander.expand = AsyncMock(side_effect=Exception("LLM error"))

        service = SeedPoolBuilderService(seasonal_seed_expander=mock_expander)

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        seasonal_seeds = [s for s in seeds if s.source == "seasonal"]
        assert len(seasonal_seeds) > 0

    @pytest.mark.asyncio
    @patch("app.services.seed_pool_builder.get_settings")
    async def test_build_seed_pool_seasonal_llm_disabled(self, mock_get_settings):
        """Test seed pool uses template when seasonal LLM is disabled."""
        mock_settings = MagicMock()
        mock_settings.seed_enable_seasonal_llm_expansion = False
        mock_get_settings.return_value = mock_settings

        mock_expander = AsyncMock()
        mock_expander.expand = AsyncMock(
            return_value=["wireless earbuds for dad"]  # Should not be called
        )

        service = SeedPoolBuilderService(seasonal_seed_expander=mock_expander)

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=20,
        )

        # Should only have template seasonal seeds
        seasonal_seeds = [s for s in seeds if s.source == "seasonal"]
        seasonal_llm_seeds = [s for s in seeds if s.source == "seasonal_llm"]
        assert len(seasonal_seeds) > 0
        assert len(seasonal_llm_seeds) == 0

    @pytest.mark.asyncio
    async def test_build_seed_pool_no_region_uses_template(self):
        """Test seed pool uses template when no region provided."""
        mock_expander = AsyncMock()
        mock_expander.expand = AsyncMock(
            return_value=["wireless earbuds for dad"]  # Should not be called
        )

        service = SeedPoolBuilderService(seasonal_seed_expander=mock_expander)

        seeds = await service.build_seed_pool(
            category="electronics",
            user_keywords=None,
            region=None,  # No region
            platform="amazon",
            max_seeds=20,
        )

        # Should only have template seasonal seeds
        seasonal_seeds = [s for s in seeds if s.source == "seasonal"]
        seasonal_llm_seeds = [s for s in seeds if s.source == "seasonal_llm"]
        assert len(seasonal_seeds) > 0
        assert len(seasonal_llm_seeds) == 0
        mock_expander.expand.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_seed_pool_exploration_mode_with_seasonal_llm(self):
        """Test seed pool with seasonal LLM expansion in exploration mode (no category)."""
        mock_expander = AsyncMock()
        # Mock expander to return different phrases for different categories
        async def mock_expand(event, category, region, limit):
            if category == "electronics":
                return ["wireless earbuds", "phone stand"]
            elif category == "jewelry":
                return ["necklace gift", "bracelet set"]
            return []

        mock_expander.expand = AsyncMock(side_effect=mock_expand)

        service = SeedPoolBuilderService(seasonal_seed_expander=mock_expander)

        seeds = await service.build_seed_pool(
            category=None,  # Exploration mode
            user_keywords=None,
            region="US",
            platform="amazon",
            max_seeds=50,
        )

        seasonal_llm_seeds = [s for s in seeds if s.source == "seasonal_llm"]
        # Should have seasonal_llm seeds from multiple event categories
        assert len(seasonal_llm_seeds) > 0
        # Verify expander was called with actual categories (not None)
        assert mock_expander.expand.call_count > 0
        for call in mock_expander.expand.call_args_list:
            _, kwargs = call
            assert kwargs["category"] is not None
            assert kwargs["category"] in ["electronics", "jewelry", "fashion", "home", "sports", "toys", "fitness", "beauty"]


