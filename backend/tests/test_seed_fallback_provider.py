"""Tests for SeedFallbackProvider."""
import pytest
from unittest.mock import patch

from app.services.seed_fallback_provider import SeedFallbackProvider


@pytest.mark.asyncio
async def test_category_hotwords_returned_first():
    """Category hotwords should be returned first when category is provided."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=1,
        category_hotword_limit=2,
    )

    result = await provider.get_candidate_fallback_keywords(
        category="手机配件",
        limit=5,
    )

    assert len(result) >= 2
    assert result[0][1] == "category_hotword"
    assert result[1][1] == "category_hotword"
    assert result[0][0] in ["磁吸手机壳", "透明手机壳", "防摔手机壳"]


@pytest.mark.asyncio
async def test_seasonal_seeds_returned_after_category():
    """Seasonal seeds should be returned after category hotwords."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=1,
        category_hotword_limit=2,
    )

    with patch("app.services.seed_fallback_provider.datetime") as mock_datetime:
        mock_datetime.now.return_value.month = 6  # Summer

        result = await provider.get_candidate_fallback_keywords(
            category="手机配件",
            limit=5,
        )

        # Should have 2 category hotwords + 1 seasonal seed
        assert len(result) >= 3
        seasonal_results = [r for r in result if r[1] == "seasonal"]
        assert len(seasonal_results) == 1
        assert seasonal_results[0][0] in ["夏季新品", "夏装", "夏季热销"]


@pytest.mark.asyncio
async def test_cold_start_seeds_returned_last():
    """Cold start seeds should be returned last."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品", "爆款"],
        seasonal_seed_limit=1,
        category_hotword_limit=2,
    )

    with patch("app.services.seed_fallback_provider.datetime") as mock_datetime:
        mock_datetime.now.return_value.month = 6  # Summer

        result = await provider.get_candidate_fallback_keywords(
            category="手机配件",
            limit=10,
        )

        # Should have category + seasonal + cold start
        cold_start_results = [r for r in result if r[1] == "cold_start"]
        assert len(cold_start_results) > 0
        # Cold start should come after category and seasonal
        cold_start_index = next(i for i, r in enumerate(result) if r[1] == "cold_start")
        assert cold_start_index >= 3  # After 2 category + 1 seasonal


@pytest.mark.asyncio
async def test_limit_enforced():
    """Limit parameter should be enforced."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品", "爆款", "推荐"],
        seasonal_seed_limit=2,
        category_hotword_limit=3,
    )

    result = await provider.get_candidate_fallback_keywords(
        category="手机配件",
        limit=3,
    )

    assert len(result) == 3


@pytest.mark.asyncio
async def test_no_category_skips_hotwords():
    """When no category provided, should skip category hotwords."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=1,
        category_hotword_limit=2,
    )

    with patch("app.services.seed_fallback_provider.datetime") as mock_datetime:
        mock_datetime.now.return_value.month = 6  # Summer

        result = await provider.get_candidate_fallback_keywords(
            category=None,
            limit=5,
        )

        # Should only have seasonal + cold start
        category_results = [r for r in result if r[1] == "category_hotword"]
        assert len(category_results) == 0
        assert result[0][1] == "seasonal"


@pytest.mark.asyncio
async def test_unknown_category_returns_seasonal_and_cold_start():
    """Unknown category should skip hotwords and return seasonal + cold start."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=1,
        category_hotword_limit=2,
    )

    with patch("app.services.seed_fallback_provider.datetime") as mock_datetime:
        mock_datetime.now.return_value.month = 6  # Summer

        result = await provider.get_candidate_fallback_keywords(
            category="unknown_category_xyz",
            limit=5,
        )

        # Should skip category hotwords for unknown category
        category_results = [r for r in result if r[1] == "category_hotword"]
        assert len(category_results) == 0
        assert result[0][1] == "seasonal"


@pytest.mark.asyncio
async def test_seasonal_seed_limit_enforced():
    """Seasonal seed limit should be enforced."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=2,
        category_hotword_limit=0,
    )

    with patch("app.services.seed_fallback_provider.datetime") as mock_datetime:
        mock_datetime.now.return_value.month = 6  # Summer

        result = await provider.get_candidate_fallback_keywords(
            category=None,
            limit=10,
        )

        seasonal_results = [r for r in result if r[1] == "seasonal"]
        assert len(seasonal_results) == 2


@pytest.mark.asyncio
async def test_category_hotword_limit_enforced():
    """Category hotword limit should be enforced."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=0,
        category_hotword_limit=1,
    )

    result = await provider.get_candidate_fallback_keywords(
        category="手机配件",
        limit=10,
    )

    category_results = [r for r in result if r[1] == "category_hotword"]
    assert len(category_results) == 1


@pytest.mark.asyncio
async def test_season_detection():
    """Season should be detected correctly based on month."""
    provider = SeedFallbackProvider(
        cold_start_seeds=[],
        seasonal_seed_limit=1,
        category_hotword_limit=0,
    )

    # Test spring (March)
    with patch("app.services.seed_fallback_provider.datetime") as mock_datetime:
        mock_datetime.now.return_value.month = 3
        result = await provider.get_candidate_fallback_keywords(limit=1)
        assert result[0][0] in ["春季新品", "春装", "春季热销"]

    # Test summer (June)
    with patch("app.services.seed_fallback_provider.datetime") as mock_datetime:
        mock_datetime.now.return_value.month = 6
        result = await provider.get_candidate_fallback_keywords(limit=1)
        assert result[0][0] in ["夏季新品", "夏装", "夏季热销"]

    # Test autumn (September)
    with patch("app.services.seed_fallback_provider.datetime") as mock_datetime:
        mock_datetime.now.return_value.month = 9
        result = await provider.get_candidate_fallback_keywords(limit=1)
        assert result[0][0] in ["秋季新品", "秋装", "秋季热销"]

    # Test winter (December)
    with patch("app.services.seed_fallback_provider.datetime") as mock_datetime:
        mock_datetime.now.return_value.month = 12
        result = await provider.get_candidate_fallback_keywords(limit=1)
        assert result[0][0] in ["冬季新品", "冬装", "冬季热销"]


@pytest.mark.asyncio
async def test_region_specific_cold_start_seeds_us():
    """Test US region uses English cold start seeds."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=0,
        category_hotword_limit=0,
    )

    result = await provider.get_candidate_fallback_keywords(
        category=None,
        region="US",
        limit=10,
    )

    cold_start_results = [r for r in result if r[1] == "cold_start"]
    assert len(cold_start_results) > 0
    assert cold_start_results[0][0] in ["trending", "best seller", "new arrival", "gift ideas"]


@pytest.mark.asyncio
async def test_region_specific_cold_start_seeds_de():
    """Test DE region uses German cold start seeds."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=0,
        category_hotword_limit=0,
    )

    result = await provider.get_candidate_fallback_keywords(
        category=None,
        region="DE",
        limit=10,
    )

    cold_start_results = [r for r in result if r[1] == "cold_start"]
    assert len(cold_start_results) > 0
    assert cold_start_results[0][0] in ["trendartikel", "bestseller", "neuheiten", "geschenkideen"]


@pytest.mark.asyncio
async def test_region_specific_cold_start_seeds_jp():
    """Test JP region uses Japanese cold start seeds."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=0,
        category_hotword_limit=0,
    )

    result = await provider.get_candidate_fallback_keywords(
        category=None,
        region="JP",
        limit=10,
    )

    cold_start_results = [r for r in result if r[1] == "cold_start"]
    assert len(cold_start_results) > 0
    assert cold_start_results[0][0] in ["人気商品", "売れ筋", "新着", "ギフト"]


@pytest.mark.asyncio
async def test_region_specific_cold_start_seeds_cn():
    """Test CN region uses Chinese cold start seeds."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=0,
        category_hotword_limit=0,
    )

    result = await provider.get_candidate_fallback_keywords(
        category=None,
        region="CN",
        limit=10,
    )

    cold_start_results = [r for r in result if r[1] == "cold_start"]
    assert len(cold_start_results) > 0
    assert cold_start_results[0][0] in ["热销", "新品", "爆款", "推荐"]


@pytest.mark.asyncio
async def test_unknown_region_falls_back_to_us():
    """Test unknown region falls back to US cold start seeds."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=0,
        category_hotword_limit=0,
    )

    result = await provider.get_candidate_fallback_keywords(
        category=None,
        region="XX",
        limit=10,
    )

    cold_start_results = [r for r in result if r[1] == "cold_start"]
    assert len(cold_start_results) > 0
    assert cold_start_results[0][0] in ["trending", "best seller", "new arrival", "gift ideas"]


@pytest.mark.asyncio
async def test_none_region_falls_back_to_us():
    """Test None region falls back to US cold start seeds."""
    provider = SeedFallbackProvider(
        cold_start_seeds=["热销", "新品"],
        seasonal_seed_limit=0,
        category_hotword_limit=0,
    )

    result = await provider.get_candidate_fallback_keywords(
        category=None,
        region=None,
        limit=10,
    )

    cold_start_results = [r for r in result if r[1] == "cold_start"]
    assert len(cold_start_results) > 0
    assert cold_start_results[0][0] in ["trending", "best seller", "new arrival", "gift ideas"]
