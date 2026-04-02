"""End-to-end seller-first flow tests.

These tests exercise the main path across:
- DemandDiscoveryService
- ProductSelectorAgent
- source adapter handoff

The goal is to verify the system behavior from keyword discovery decisions
through selector output metadata and adapter invocation semantics.

After seller-first refactor:
- No runtime keyword generation in online path
- No validated keywords → clean skip with count=0
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.product_selector import ProductSelectorAgent
from app.core.enums import SourcePlatform
from app.services.demand_discovery_service import DemandDiscoveryService
from app.services.demand_validator import (
    CompetitionDensity,
    DemandValidationResult,
    TrendDirection,
)
from app.services.keyword_legitimizer import ValidKeyword
from app.services.seed_pool_builder import Seed
from app.services.source_adapter import ProductData


def _make_validation_result(
    keyword: str,
    *,
    passed: bool,
    search_volume: int,
    competition_density: CompetitionDensity,
    trend_direction: TrendDirection,
    rejection_reasons: list[str] | None = None,
) -> DemandValidationResult:
    return DemandValidationResult(
        keyword=keyword,
        search_volume=search_volume,
        competition_density=competition_density,
        trend_direction=trend_direction,
        trend_growth_rate=None,
        passed=passed,
        rejection_reasons=rejection_reasons or [],
    )


def _make_product_data(title: str = "Seller-first product") -> ProductData:
    return ProductData(
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="prod-1",
        source_url="https://detail.1688.com/offer/prod-1.html",
        title=title,
        category="electronics",
        currency="USD",
        platform_price=Decimal("19.99"),
        sales_count=1000,
        rating=Decimal("4.5"),
        main_image_url="https://example.com/1.jpg",
        raw_payload={},
        normalized_attributes={},
        supplier_candidates=[],
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def mock_source_adapter():
    adapter = AsyncMock()
    adapter.fetch_products.return_value = [_make_product_data()]
    return adapter


@pytest.fixture
def mock_supplier_matcher():
    matcher = AsyncMock()
    matcher.find_suppliers.return_value = []
    return matcher


def _make_mock_keyword_legitimizer():
    """Create mock keyword legitimizer that converts seeds to valid keywords."""
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


def _make_mock_seed_pool_builder():
    """Create mock seed pool builder that returns empty list by default."""
    builder = AsyncMock()
    builder.build_seed_pool.return_value = []
    return builder


def _make_mock_exploration_seed_provider():
    """Create mock exploration seed provider that returns empty list by default."""
    provider = AsyncMock()
    provider.get_exploration_seeds.return_value = []
    return provider


@pytest.mark.asyncio
async def test_no_user_keywords_use_seed_pool_and_fetch(
    mock_db,
    mock_source_adapter,
    mock_supplier_matcher,
):
    """No-keyword request should use seed pool, validate, then fetch with discovered keywords."""
    demand_validator = AsyncMock()
    demand_validator.validate_batch.return_value = [
        _make_validation_result(
            "wireless earbuds",
            passed=True,
            search_volume=8000,
            competition_density=CompetitionDensity.LOW,
            trend_direction=TrendDirection.RISING,
        )
    ]

    seed_pool_builder = _make_mock_seed_pool_builder()
    seed_pool_builder.build_seed_pool.return_value = [
        Seed(
            term="wireless earbuds",
            source="category_static",
            confidence=0.5,
            category="electronics",
            region="US",
            platform=None,
        )
    ]

    discovery_service = DemandDiscoveryService(
        demand_validator=demand_validator,
        keyword_legitimizer=_make_mock_keyword_legitimizer(),
        seed_pool_builder=seed_pool_builder,
        exploration_seed_provider=_make_mock_exploration_seed_provider(),
    )

    agent = ProductSelectorAgent(
        source_adapter=mock_source_adapter,
        supplier_matcher=mock_supplier_matcher,
        demand_discovery_service=discovery_service,
        enable_demand_validation=True,
        enable_seasonal_boost=False,
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "temu",
            "category": "electronics",
            "keywords": None,
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 1
    assert result.output_data["demand_discovery"]["discovery_mode"] == "seed_pool"
    assert result.output_data["demand_discovery"]["fallback_used"] is False
    assert result.output_data["demand_discovery"]["degraded"] is False
    assert result.output_data["demand_discovery"]["validated_keywords"][0]["keyword"] == "wireless earbuds"
    assert result.output_data["demand_discovery"]["validated_keywords"][0]["source"] == "category_static"

    mock_source_adapter.fetch_products.assert_called_once()
    assert mock_source_adapter.fetch_products.call_args.kwargs["keywords"] == ["wireless earbuds"]


@pytest.mark.asyncio
async def test_rejected_user_keywords_do_not_recover_via_generated_keywords(
    mock_db,
    mock_source_adapter,
    mock_supplier_matcher,
):
    """Rejected user keywords should not trigger fallback recovery before fetch."""
    demand_validator = AsyncMock()
    demand_validator.validate_batch.return_value = [
        _make_validation_result(
            "bad keyword",
            passed=False,
            search_volume=10,
            competition_density=CompetitionDensity.HIGH,
            trend_direction=TrendDirection.DECLINING,
            rejection_reasons=["low_search_volume"],
        )
    ]

    seed_pool_builder = _make_mock_seed_pool_builder()
    seed_pool_builder.build_seed_pool.return_value = []

    discovery_service = DemandDiscoveryService(
        demand_validator=demand_validator,
        keyword_legitimizer=_make_mock_keyword_legitimizer(),
        seed_pool_builder=seed_pool_builder,
        exploration_seed_provider=_make_mock_exploration_seed_provider(),
    )

    agent = ProductSelectorAgent(
        source_adapter=mock_source_adapter,
        supplier_matcher=mock_supplier_matcher,
        demand_discovery_service=discovery_service,
        enable_demand_validation=True,
        enable_seasonal_boost=False,
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "temu",
            "category": "electronics",
            "keywords": ["bad keyword"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 0
    assert result.output_data["skipped_reason"] == "no_validated_keywords_available"
    assert result.output_data["demand_discovery"]["discovery_mode"] == "none"
    assert result.output_data["demand_discovery"]["fallback_used"] is False
    assert result.output_data["demand_discovery"]["degraded"] is True
    assert result.output_data["demand_discovery"]["rejected_keywords"][0]["keyword"] == "bad keyword"
    assert result.output_data["demand_discovery"]["rejected_keywords"][0]["source"] == "user"

    mock_source_adapter.fetch_products.assert_not_called()


@pytest.mark.asyncio
async def test_empty_seed_pool_skips_cleanly(
    mock_db,
    mock_source_adapter,
    mock_supplier_matcher,
):
    """Empty seed pool should skip cleanly when no validated keywords are available."""
    demand_validator = AsyncMock()
    demand_validator.validate_batch.return_value = []

    seed_pool_builder = _make_mock_seed_pool_builder()
    seed_pool_builder.build_seed_pool.return_value = []

    discovery_service = DemandDiscoveryService(
        demand_validator=demand_validator,
        keyword_legitimizer=_make_mock_keyword_legitimizer(),
        seed_pool_builder=seed_pool_builder,
        exploration_seed_provider=_make_mock_exploration_seed_provider(),
    )

    agent = ProductSelectorAgent(
        source_adapter=mock_source_adapter,
        supplier_matcher=mock_supplier_matcher,
        demand_discovery_service=discovery_service,
        enable_demand_validation=True,
        enable_seasonal_boost=False,
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "temu",
            "category": "electronics",
            "keywords": None,
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 0
    assert result.output_data["skipped_reason"] == "no_validated_keywords_available"
    mock_source_adapter.fetch_products.assert_not_called()
