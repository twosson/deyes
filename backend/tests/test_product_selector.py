"""Tests for ProductSelectorAgent demand-first behavior."""
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
from app.services.source_adapter import ProductData


@pytest.mark.asyncio
async def test_product_selector_uses_demand_discovery_before_fetching():
    """Selector should fetch products only with demand-discovered keywords."""
    mock_adapter = AsyncMock()
    mock_adapter.fetch_products.return_value = [
        ProductData(
            source_platform=SourcePlatform.ALIBABA_1688,
            source_product_id="prod-1",
            source_url="https://detail.1688.com/offer/prod-1.html",
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
    mock_discovery.discover_keywords.assert_called_once()
    mock_adapter.fetch_products.assert_called_once()
    assert mock_adapter.fetch_products.call_args.kwargs["keywords"] == ["validated keyword"]


@pytest.mark.asyncio
async def test_product_selector_skips_fetch_when_no_validated_keywords():
    """Selector should skip source fetch when demand discovery returns no validated keywords."""
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
    assert result.output_data["demand_discovery"]["degraded"] is True
    mock_adapter.fetch_products.assert_not_called()
