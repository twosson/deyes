"""End-to-end demand-first flow tests.

These tests exercise the main path across:
- DemandDiscoveryService
- ProductSelectorAgent
- source adapter handoff

The goal is to verify the system behavior from keyword discovery decisions
through selector output metadata and adapter invocation semantics.

After fail-fast refactor:
- No fallback seeds are used
- No validated keywords → RuntimeError → success=False
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
from app.services.keyword_generator import KeywordResult
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


def _make_product_data(title: str = "Demand-first product") -> ProductData:
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
async def test_no_user_keywords_generate_validate_and_fetch(
    mock_db,
    mock_source_adapter,
    mock_supplier_matcher,
):
    """No-keyword request should generate, validate, then fetch with discovered keywords."""
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

    keyword_generator = AsyncMock()
    keyword_generator.generate_selection_keywords.return_value = [
        KeywordResult(
            keyword="wireless earbuds",
            search_volume=8000,
            trend_score=85,
            competition_density=CompetitionDensity.LOW,
            related_keywords=["bluetooth earbuds"],
            category="electronics",
            region="US",
        )
    ]

    discovery_service = DemandDiscoveryService(
        demand_validator=demand_validator,
        keyword_generator=keyword_generator,
        keyword_legitimizer=_make_mock_keyword_legitimizer(),
        seed_pool_builder=_make_mock_seed_pool_builder(),
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
            "platform": "alibaba_1688",
            "category": "electronics",
            "keywords": None,
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 1
    assert result.output_data["demand_discovery"]["discovery_mode"] == "generated"
    assert result.output_data["demand_discovery"]["fallback_used"] is False
    assert result.output_data["demand_discovery"]["degraded"] is False
    assert result.output_data["demand_discovery"]["validated_keywords"][0]["keyword"] == "wireless earbuds"
    assert result.output_data["demand_discovery"]["validated_keywords"][0]["source"] == "generated"

    mock_source_adapter.fetch_products.assert_called_once()
    assert mock_source_adapter.fetch_products.call_args.kwargs["keywords"] == ["wireless earbuds"]


@pytest.mark.asyncio
async def test_rejected_user_keywords_recover_via_generated_keywords(
    mock_db,
    mock_source_adapter,
    mock_supplier_matcher,
):
    """Rejected user keywords should degrade into generated recovery before fetch."""
    demand_validator = AsyncMock()
    demand_validator.validate_batch.side_effect = [
        [
            _make_validation_result(
                "bad keyword",
                passed=False,
                search_volume=10,
                competition_density=CompetitionDensity.HIGH,
                trend_direction=TrendDirection.DECLINING,
                rejection_reasons=["low_search_volume"],
            )
        ],
        [
            _make_validation_result(
                "trending product",
                passed=True,
                search_volume=9000,
                competition_density=CompetitionDensity.LOW,
                trend_direction=TrendDirection.RISING,
            )
        ],
    ]

    keyword_generator = AsyncMock()
    keyword_generator.generate_selection_keywords.return_value = [
        KeywordResult(
            keyword="trending product",
            search_volume=9000,
            trend_score=88,
            competition_density=CompetitionDensity.LOW,
            related_keywords=[],
            category="electronics",
            region="US",
        )
    ]

    discovery_service = DemandDiscoveryService(
        demand_validator=demand_validator,
        keyword_generator=keyword_generator,
        keyword_legitimizer=_make_mock_keyword_legitimizer(),
        seed_pool_builder=_make_mock_seed_pool_builder(),
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
            "platform": "alibaba_1688",
            "category": "electronics",
            "keywords": ["bad keyword"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 1
    assert result.output_data["demand_discovery"]["discovery_mode"] == "generated"
    assert result.output_data["demand_discovery"]["fallback_used"] is False
    assert result.output_data["demand_discovery"]["degraded"] is True
    assert result.output_data["demand_discovery"]["validated_keywords"][0]["keyword"] == "trending product"
    assert result.output_data["demand_discovery"]["rejected_keywords"][0]["keyword"] == "bad keyword"
    assert result.output_data["demand_discovery"]["rejected_keywords"][0]["source"] == "user"

    mock_source_adapter.fetch_products.assert_called_once()
    assert mock_source_adapter.fetch_products.call_args.kwargs["keywords"] == ["trending product"]


@pytest.mark.asyncio
async def test_generation_failure_fails_fast(
    mock_db,
    mock_source_adapter,
    mock_supplier_matcher,
):
    """Generation failure should cause agent to fail fast with error."""
    demand_validator = AsyncMock()
    demand_validator.validate_batch.return_value = []

    keyword_generator = AsyncMock()
    keyword_generator.generate_selection_keywords.side_effect = RuntimeError("generator down")

    discovery_service = DemandDiscoveryService(
        demand_validator=demand_validator,
        keyword_generator=keyword_generator,
        keyword_legitimizer=_make_mock_keyword_legitimizer(),
        seed_pool_builder=_make_mock_seed_pool_builder(),
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
            "platform": "alibaba_1688",
            "category": "electronics",
            "keywords": None,
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is False
    assert "No validated keywords available" in result.error_message
    mock_source_adapter.fetch_products.assert_not_called()


@pytest.mark.asyncio
async def test_zero_keyword_fails_fast(
    mock_db,
    mock_source_adapter,
    mock_supplier_matcher,
):
    """When nothing validates, selector should fail fast with error."""
    demand_validator = AsyncMock()
    demand_validator.validate_batch.return_value = []

    keyword_generator = AsyncMock()
    keyword_generator.generate_selection_keywords.return_value = []

    discovery_service = DemandDiscoveryService(
        demand_validator=demand_validator,
        keyword_generator=keyword_generator,
        keyword_legitimizer=_make_mock_keyword_legitimizer(),
        seed_pool_builder=_make_mock_seed_pool_builder(),
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
            "platform": "alibaba_1688",
            "category": "electronics",
            "keywords": None,
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is False
    assert "No validated keywords available" in result.error_message
    mock_source_adapter.fetch_products.assert_not_called()
