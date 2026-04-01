"""Tests for ExplorationSeedProvider."""
import pytest

from app.services.exploration_seed_provider import (
    ExplorationBrief,
    ExplorationSeedProvider,
)


@pytest.mark.asyncio
async def test_get_exploration_seeds_returns_trend_and_supply():
    """Provider should return trend and supply seeds."""
    provider = ExplorationSeedProvider()
    brief = ExplorationBrief(
        region="US",
        platform="Amazon",
        max_seeds=10,
        min_confidence=0.3,
    )

    seeds = await provider.get_exploration_seeds(brief)

    assert len(seeds) > 0
    assert all(seed.confidence >= 0.3 for seed in seeds)
    assert any(seed.source == "trend" for seed in seeds)
    assert any(seed.source == "supply" for seed in seeds)


@pytest.mark.asyncio
async def test_get_exploration_seeds_respects_max_seeds():
    """Provider should respect max_seeds limit."""
    provider = ExplorationSeedProvider()
    brief = ExplorationBrief(
        region="US",
        platform="Amazon",
        max_seeds=5,
        min_confidence=0.3,
    )

    seeds = await provider.get_exploration_seeds(brief)

    assert len(seeds) <= 5


@pytest.mark.asyncio
async def test_get_exploration_seeds_filters_by_confidence():
    """Provider should filter seeds by min_confidence."""
    provider = ExplorationSeedProvider()
    brief = ExplorationBrief(
        region="US",
        platform="Amazon",
        max_seeds=20,
        min_confidence=0.5,
    )

    seeds = await provider.get_exploration_seeds(brief)

    assert all(seed.confidence >= 0.5 for seed in seeds)


@pytest.mark.asyncio
async def test_get_exploration_seeds_returns_region_specific_supply():
    """Provider should return region-specific supply seeds."""
    provider = ExplorationSeedProvider()
    brief_us = ExplorationBrief(
        region="US",
        platform="Amazon",
        max_seeds=10,
        min_confidence=0.3,
    )
    brief_cn = ExplorationBrief(
        region="CN",
        platform="Amazon",
        max_seeds=10,
        min_confidence=0.3,
    )

    seeds_us = await provider.get_exploration_seeds(brief_us)
    seeds_cn = await provider.get_exploration_seeds(brief_cn)

    us_terms = {seed.term for seed in seeds_us if seed.source == "supply"}
    cn_terms = {seed.term for seed in seeds_cn if seed.source == "supply"}

    # US and CN should have different supply seeds
    assert us_terms != cn_terms
    assert any("phone accessories" in term for term in us_terms)
    assert any("数码配件" in term for term in cn_terms)


@pytest.mark.asyncio
async def test_get_exploration_seeds_sorts_by_confidence():
    """Provider should sort seeds by confidence descending."""
    provider = ExplorationSeedProvider()
    brief = ExplorationBrief(
        region="US",
        platform="Amazon",
        max_seeds=20,
        min_confidence=0.0,
    )

    seeds = await provider.get_exploration_seeds(brief)

    confidences = [seed.confidence for seed in seeds]
    assert confidences == sorted(confidences, reverse=True)
