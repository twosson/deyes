"""Tests for ProductSelectorAgent seller-first behavior."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.product_selector import ProductSelectorAgent
from app.core.enums import SourcePlatform
from app.services.demand_validator import (
    CompetitionDensity,
    DemandValidationResult,
    TrendDirection,
)
from app.services.demand_discovery_service import DemandDiscoveryKeyword, DemandDiscoveryResult
from app.services.opportunity_discovery_service import OpportunityDraft
from app.services.source_adapter import ProductData


@pytest.mark.asyncio
async def test_product_selector_uses_demand_discovery_before_fetching():
    """Selector should fetch products only with demand-discovered keywords (non-1688 platform)."""
    mock_adapter = AsyncMock()
    mock_adapter.fetch_products.return_value = [
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod-1",
            source_url="https://www.temu.com/prod-1.html",
            title="Validated Product",
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
    ]

    mock_supplier_matcher = AsyncMock()
    mock_supplier_matcher.find_suppliers.return_value = []

    mock_discovery = AsyncMock()
    mock_discovery.discover_keywords.return_value = DemandDiscoveryResult(
        validated_keywords=[
            DemandDiscoveryKeyword(
                keyword="validated keyword",
                source="generated",
                validation=DemandValidationResult(
                    keyword="validated keyword",
                    search_volume=5000,
                    competition_density=CompetitionDensity.LOW,
                    trend_direction=TrendDirection.RISING,
                    trend_growth_rate=None,
                ),
            )
        ],
        rejected_keywords=[],
        discovery_mode="generated",
        fallback_used=False,
        degraded=False,
    )

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        demand_discovery_service=mock_discovery,
        enable_demand_validation=True,
        enable_seasonal_boost=False,
    )
    agent.logger = MagicMock()

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
    assert result.output_data["demand_discovery"]["discovery_mode"] == "generated"
    mock_discovery.discover_keywords.assert_called_once()
    assert mock_discovery.discover_keywords.call_args.kwargs["platform"] == "temu"
    mock_adapter.fetch_products.assert_called_once()
    assert mock_adapter.fetch_products.call_args.kwargs["keywords"] == ["validated keyword"]
    agent.logger.info.assert_any_call(
        "product_selection_metrics",
        strategy_run_id=str(context.strategy_run_id),
        category="electronics",
        region="US",
        platform="temu",
        discovery_mode="generated",
        skipped=False,
        skip_rate=0.0,
        selection_triggered_per_category=1,
        candidate_count_per_discovery_mode=1,
        validated_keywords_count=1,
    )


@pytest.mark.asyncio
async def test_product_selector_uses_opportunity_products_for_1688():
    """Selector should use opportunity report products directly on 1688."""
    mock_adapter = AsyncMock()
    mock_adapter.fetch_products.return_value = []

    mock_supplier_matcher = AsyncMock()
    mock_supplier_matcher.find_suppliers.return_value = []

    mock_discovery = AsyncMock()
    mock_discovery.discover_keywords.return_value = DemandDiscoveryResult(
        validated_keywords=[
            DemandDiscoveryKeyword(
                keyword="tablet stand",
                source="user",
                validation=DemandValidationResult(
                    keyword="tablet stand",
                    search_volume=5000,
                    competition_density=CompetitionDensity.LOW,
                    trend_direction=TrendDirection.RISING,
                    trend_growth_rate=None,
                ),
            )
        ],
        rejected_keywords=[],
        discovery_mode="user",
        fallback_used=False,
        degraded=False,
        valid_keywords=[
            {
                "seed": {
                    "term": "tablet stand",
                    "source": "user",
                    "confidence": 1.0,
                    "category": "electronics",
                    "region": "US",
                    "platform": "Amazon",
                },
                "matched_keyword": "tablet stand",
                "match_type": "exact",
                "opp_score": 82.0,
                "search_volume": 5000,
                "competition_density": "low",
                "is_valid_for_report": True,
                "raw": {"keyword": "tablet stand", "keywordCn": "平板支架"},
                "report_keyword": "tablet stand",
                "keyword_cn": "平板支架",
                "sold_cnt_30d": 139000,
                "growth_rate": 0.06,
            }
        ],
    )

    mock_opportunity_service = AsyncMock()
    mock_opportunity_service.discover_opportunities.return_value = [
        OpportunityDraft(
            keyword="tablet stand",
            title="Rising tablet stand demand",
            opportunity_score=88.0,
            product_list=[
                {
                    "productId": "report-prod-1",
                    "title": "Adjustable Tablet Stand",
                    "detailUrl": "https://detail.1688.com/offer/report-prod-1.html",
                    "imageUrl": "https://example.com/report-1.jpg",
                    "price": "12.50",
                    "salesCount": 3200,
                    "category": "electronics",
                }
            ],
            keyword_summary={"summary": "Rising tablet stand demand", "opportunityScore": 88},
            evidence={"report_keyword": "tablet stand", "product_count": 1},
            raw={"request_id": "req-1"},
        )
    ]

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        demand_discovery_service=mock_discovery,
        opportunity_discovery_service=mock_opportunity_service,
        enable_demand_validation=True,
        enable_seasonal_boost=False,
    )
    agent.logger = MagicMock()

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "alibaba_1688",
            "category": "electronics",
            "keywords": ["tablet stand"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 1
    mock_adapter.fetch_products.assert_called_once()
    assert mock_adapter.fetch_products.call_args.kwargs["keywords"] == ["平板支架"]
    mock_opportunity_service.discover_opportunities.assert_called_once()
    mock_supplier_matcher.find_suppliers.assert_called_once()

    candidate = mock_db.add.call_args_list[0].args[0]
    assert candidate.source_product_id == "report-prod-1"
    assert candidate.title == "Adjustable Tablet Stand"
    assert candidate.normalized_attributes["matched_keyword"] == "tablet stand"
    assert candidate.normalized_attributes["report_keyword"] == "tablet stand"
    assert candidate.normalized_attributes["opportunity_keyword"] == "tablet stand"
    assert candidate.normalized_attributes["opportunity_score"] == 88.0
    assert candidate.normalized_attributes["search_intelligence"]["keyword_cn"] == "平板支架"
    assert candidate.normalized_attributes["supply_query"] == "平板支架"
    assert candidate.demand_discovery_metadata["opportunity"]["keyword"] == "tablet stand"


@pytest.mark.asyncio
async def test_product_selector_skips_when_no_validated_keywords():
    """Selector should skip (success=True, count=0) when demand discovery returns no validated keywords."""
    mock_adapter = AsyncMock()
    mock_supplier_matcher = AsyncMock()

    mock_discovery = AsyncMock()
    mock_discovery.discover_keywords.return_value = DemandDiscoveryResult(
        validated_keywords=[],
        rejected_keywords=[
            DemandDiscoveryKeyword(
                keyword="bad keyword",
                source="user",
                validation=DemandValidationResult(
                    keyword="bad keyword",
                    search_volume=10,
                    competition_density=CompetitionDensity.HIGH,
                    trend_direction=TrendDirection.DECLINING,
                    trend_growth_rate=None,
                ),
            )
        ],
        discovery_mode="none",
        fallback_used=False,
        degraded=True,
    )

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        demand_discovery_service=mock_discovery,
        enable_demand_validation=True,
        enable_seasonal_boost=False,
    )
    agent.logger = MagicMock()

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
    assert result.output_data["count"] == 0
    assert result.output_data["skipped_reason"] == "no_validated_keywords_available"
    assert result.output_data["demand_discovery"]["discovery_mode"] == "none"
    mock_adapter.fetch_products.assert_not_called()


@pytest.mark.asyncio
async def test_product_selector_1688_uses_supply_validation_when_no_opportunities():
    """1688 should use search-intelligence supply validation as the primary path when no opportunities exist."""
    mock_adapter = AsyncMock()
    mock_adapter.fetch_products.return_value = [
        ProductData(
            source_platform=SourcePlatform.ALIBABA_1688,
            source_product_id="supply-prod-1",
            source_url="https://detail.1688.com/offer/supply-prod-1.html",
            title="平板支架 Adjustable Tablet Stand",
            category="electronics",
            currency="USD",
            platform_price=Decimal("9.99"),
            sales_count=1200,
            rating=None,
            main_image_url="https://example.com/supply-1.jpg",
            raw_payload={},
            normalized_attributes={"matched_keyword": "平板支架"},
            supplier_candidates=[],
        )
    ]

    mock_supplier_matcher = AsyncMock()
    mock_supplier_matcher.find_suppliers.return_value = []

    mock_discovery = AsyncMock()
    mock_discovery.discover_keywords.return_value = DemandDiscoveryResult(
        validated_keywords=[
            DemandDiscoveryKeyword(
                keyword="tablet stand",
                source="user",
                validation=DemandValidationResult(
                    keyword="tablet stand",
                    search_volume=5000,
                    competition_density=CompetitionDensity.LOW,
                    trend_direction=TrendDirection.RISING,
                    trend_growth_rate=None,
                ),
            )
        ],
        rejected_keywords=[],
        discovery_mode="user",
        fallback_used=False,
        degraded=False,
        valid_keywords=[
            {
                "seed": {
                    "term": "tablet stand",
                    "source": "user",
                    "confidence": 1.0,
                    "category": "electronics",
                    "region": "US",
                    "platform": "Amazon",
                },
                "matched_keyword": "tablet stand",
                "match_type": "exact",
                "opp_score": 82.0,
                "search_volume": 5000,
                "competition_density": "low",
                "is_valid_for_report": True,
                "raw": {"keyword": "tablet stand", "keywordCn": "平板支架"},
                "report_keyword": "tablet stand",
                "keyword_cn": "平板支架",
            }
        ],
    )

    mock_opportunity_service = AsyncMock()
    mock_opportunity_service.discover_opportunities.return_value = []

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        demand_discovery_service=mock_discovery,
        opportunity_discovery_service=mock_opportunity_service,
        enable_demand_validation=True,
        enable_seasonal_boost=False,
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "alibaba_1688",
            "category": "electronics",
            "keywords": ["tablet stand"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 1
    mock_opportunity_service.discover_opportunities.assert_called_once()
    mock_adapter.fetch_products.assert_called_once()
    assert mock_adapter.fetch_products.call_args.kwargs["keywords"] == ["平板支架"]

    candidate = mock_db.add.call_args_list[0].args[0]
    assert candidate.source_product_id == "supply-prod-1"
    assert candidate.normalized_attributes["search_intelligence"]["keyword_cn"] == "平板支架"
    assert candidate.normalized_attributes["matched_keyword"] == "平板支架"
    assert candidate.normalized_attributes["report_keyword"] == "tablet stand"
    assert candidate.normalized_attributes["supply_query"] == "平板支架"
    assert candidate.demand_discovery_metadata["valid_keywords"][0]["keyword_cn"] == "平板支架"


@pytest.mark.asyncio
async def test_product_selector_1688_skips_when_no_opportunities_or_supply_candidates():
    """1688 should cleanly skip when both opportunity enhancement and supply validation return no products."""
    mock_adapter = AsyncMock()
    mock_adapter.fetch_products.return_value = []

    mock_supplier_matcher = AsyncMock()
    mock_supplier_matcher.find_suppliers.return_value = []

    mock_discovery = AsyncMock()
    mock_discovery.discover_keywords.return_value = DemandDiscoveryResult(
        validated_keywords=[
            DemandDiscoveryKeyword(
                keyword="tablet stand",
                source="user",
                validation=DemandValidationResult(
                    keyword="tablet stand",
                    search_volume=5000,
                    competition_density=CompetitionDensity.LOW,
                    trend_direction=TrendDirection.RISING,
                    trend_growth_rate=None,
                ),
            )
        ],
        rejected_keywords=[],
        discovery_mode="user",
        fallback_used=False,
        degraded=False,
        valid_keywords=[
            {
                "seed": {
                    "term": "tablet stand",
                    "source": "user",
                    "confidence": 1.0,
                },
                "matched_keyword": "tablet stand",
                "match_type": "exact",
                "opp_score": 82.0,
                "search_volume": 5000,
                "competition_density": "low",
                "is_valid_for_report": True,
                "raw": {"keyword": "tablet stand", "keywordCn": "平板支架"},
                "report_keyword": "tablet stand",
                "keyword_cn": "平板支架",
            }
        ],
    )

    mock_opportunity_service = AsyncMock()
    mock_opportunity_service.discover_opportunities.return_value = []

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        demand_discovery_service=mock_discovery,
        opportunity_discovery_service=mock_opportunity_service,
        enable_demand_validation=True,
        enable_seasonal_boost=False,
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "alibaba_1688",
            "category": "electronics",
            "keywords": ["tablet stand"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 0
    assert result.output_data["skipped_reason"] == "no_supply_candidates_available"
    mock_opportunity_service.discover_opportunities.assert_called_once()
    mock_adapter.fetch_products.assert_called_once()


@pytest.mark.asyncio
async def test_product_selector_1688_supply_products_bypass_strict_relevance_filter():
    """Supply-only products should bypass strict opportunity relevance threshold.

    Regression test: supply products recalled via search intelligence should not
    be rejected by _filter_products_by_opportunity_relevance even if their title
    doesn't text-match the opportunity/report keyword.
    """
    mock_adapter = AsyncMock()
    # Supply product with Chinese title that doesn't contain English "tablet stand"
    mock_adapter.fetch_products.return_value = [
        ProductData(
            source_platform=SourcePlatform.ALIBABA_1688,
            source_product_id="supply-prod-1",
            source_url="https://detail.1688.com/offer/supply-prod-1.html",
            title="铝合金桌面手机架可调节高度创意简约",  # No "平板支架" or "tablet stand"
            category="electronics",
            currency="USD",
            platform_price=Decimal("9.99"),
            sales_count=1200,
            rating=None,
            main_image_url="https://example.com/supply-1.jpg",
            raw_payload={},
            normalized_attributes={"matched_keyword": "平板支架"},
            supplier_candidates=[],
        )
    ]

    mock_supplier_matcher = AsyncMock()
    mock_supplier_matcher.find_suppliers.return_value = []

    mock_discovery = AsyncMock()
    mock_discovery.discover_keywords.return_value = DemandDiscoveryResult(
        validated_keywords=[
            DemandDiscoveryKeyword(
                keyword="tablet stand",
                source="user",
                validation=DemandValidationResult(
                    keyword="tablet stand",
                    search_volume=5000,
                    competition_density=CompetitionDensity.LOW,
                    trend_direction=TrendDirection.RISING,
                    trend_growth_rate=None,
                ),
            )
        ],
        rejected_keywords=[],
        discovery_mode="user",
        fallback_used=False,
        degraded=False,
        valid_keywords=[
            {
                "seed": {
                    "term": "tablet stand",
                    "source": "user",
                    "confidence": 1.0,
                    "category": "electronics",
                    "region": "US",
                    "platform": "Amazon",
                },
                "matched_keyword": "tablet stand",
                "match_type": "exact",
                "opp_score": 82.0,
                "search_volume": 5000,
                "competition_density": "low",
                "is_valid_for_report": True,
                "raw": {"keyword": "tablet stand", "keywordCn": "平板支架"},
                "report_keyword": "tablet stand",
                "keyword_cn": "平板支架",
            }
        ],
    )

    mock_opportunity_service = AsyncMock()
    mock_opportunity_service.discover_opportunities.return_value = []

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        demand_discovery_service=mock_discovery,
        opportunity_discovery_service=mock_opportunity_service,
        enable_demand_validation=True,
        enable_seasonal_boost=False,
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "alibaba_1688",
            "category": "electronics",
            "keywords": ["tablet stand"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    # Should succeed with 1 candidate despite title not matching keyword
    assert result.success is True
    assert result.output_data["count"] == 1
    mock_adapter.fetch_products.assert_called_once()
    assert mock_adapter.fetch_products.call_args.kwargs["keywords"] == ["平板支架"]

    candidate = mock_db.add.call_args_list[0].args[0]
    assert candidate.source_product_id == "supply-prod-1"
    assert candidate.normalized_attributes["matched_keyword"] == "平板支架"
    assert mock_adapter.fetch_products.call_args.kwargs["keywords"] == ["平板支架"]
    mock_db.add.assert_not_called()
