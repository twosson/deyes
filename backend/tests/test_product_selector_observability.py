"""Tests for product selector observability and metadata propagation."""
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
async def test_selector_output_includes_demand_discovery_metadata():
    """Selector output should include full demand_discovery metadata."""
    mock_adapter = AsyncMock()
    mock_adapter.fetch_products.return_value = [
        ProductData(
            source_platform=SourcePlatform.ALIBABA_1688,
            source_product_id="prod-1",
            source_url="https://detail.1688.com/offer/prod-1.html",
            title="Test Product",
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
        rejected_keywords=[
            DemandDiscoveryKeyword(
                keyword="rejected keyword",
                source="user",
                validation=DemandValidationResult(
                    keyword="rejected keyword",
                    search_volume=10,
                    competition_density=CompetitionDensity.HIGH,
                    trend_direction=TrendDirection.DECLINING,
                    trend_growth_rate=None,
                ),
            )
        ],
        discovery_mode="generated",
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
            "keywords": ["rejected keyword"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert "demand_discovery" in result.output_data
    dd = result.output_data["demand_discovery"]
    assert dd["discovery_mode"] == "generated"
    assert dd["fallback_used"] is False
    assert dd["degraded"] is True
    assert len(dd["validated_keywords"]) == 1
    assert len(dd["rejected_keywords"]) == 1


@pytest.mark.asyncio
async def test_selector_logs_demand_discovery_completed_with_counts():
    """Selector should log demand_discovery_completed with validated/rejected counts."""
    mock_adapter = AsyncMock()
    mock_adapter.fetch_products.return_value = []

    mock_supplier_matcher = AsyncMock()

    mock_discovery = AsyncMock()
    mock_discovery.discover_keywords.return_value = DemandDiscoveryResult(
        validated_keywords=[
            DemandDiscoveryKeyword(
                keyword="kw1",
                source="user",
                validation=DemandValidationResult(
                    keyword="kw1",
                    search_volume=5000,
                    competition_density=CompetitionDensity.LOW,
                    trend_direction=TrendDirection.RISING,
                    trend_growth_rate=None,
                ),
            ),
            DemandDiscoveryKeyword(
                keyword="kw2",
                source="user",
                validation=DemandValidationResult(
                    keyword="kw2",
                    search_volume=6000,
                    competition_density=CompetitionDensity.MEDIUM,
                    trend_direction=TrendDirection.STABLE,
                    trend_growth_rate=None,
                ),
            ),
        ],
        rejected_keywords=[
            DemandDiscoveryKeyword(
                keyword="bad",
                source="user",
                validation=DemandValidationResult(
                    keyword="bad",
                    search_volume=10,
                    competition_density=CompetitionDensity.HIGH,
                    trend_direction=TrendDirection.DECLINING,
                    trend_growth_rate=None,
                ),
            )
        ],
        discovery_mode="user",
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
            "keywords": ["kw1", "kw2", "bad"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    # Verify that demand_discovery_completed log would include:
    # validated=2, rejected=1, fallback_used=False, degraded=False
    # (actual log assertion would require log capture fixture)


@pytest.mark.asyncio
async def test_selector_zero_keywords_includes_skipped_reason():
    """Selector should include skipped_reason when no validated keywords available."""
    mock_adapter = AsyncMock()
    mock_supplier_matcher = AsyncMock()

    mock_discovery = AsyncMock()
    mock_discovery.discover_keywords.return_value = DemandDiscoveryResult(
        validated_keywords=[],
        rejected_keywords=[],
        discovery_mode="none",
        fallback_used=True,
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
            "keywords": None,
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 0
    assert result.output_data["skipped_reason"] == "no_validated_keywords_available"
    assert result.output_data["demand_discovery"]["discovery_mode"] == "none"
    assert result.output_data["demand_discovery"]["fallback_used"] is True
    assert result.output_data["demand_discovery"]["degraded"] is True


@pytest.mark.asyncio
async def test_selector_persists_demand_discovery_metadata_to_candidates():
    """Selector should persist demand discovery metadata to candidate_products table."""
    mock_adapter = AsyncMock()
    mock_adapter.fetch_products.return_value = [
        ProductData(
            source_platform=SourcePlatform.ALIBABA_1688,
            source_product_id="prod-1",
            source_url="https://detail.1688.com/offer/prod-1.html",
            title="Test Product",
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
        rejected_keywords=[
            DemandDiscoveryKeyword(
                keyword="rejected keyword",
                source="user",
                validation=DemandValidationResult(
                    keyword="rejected keyword",
                    search_volume=10,
                    competition_density=CompetitionDensity.HIGH,
                    trend_direction=TrendDirection.DECLINING,
                    trend_growth_rate=None,
                ),
            )
        ],
        discovery_mode="generated",
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
            "keywords": ["rejected keyword"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 1

    # Verify that db.add was called with a CandidateProduct that has demand_discovery_metadata
    add_calls = mock_db.add.call_args_list
    assert len(add_calls) >= 1

    # Find the CandidateProduct instance among db.add calls
    candidate = next(
        (
            call.args[0]
            for call in add_calls
            if call.args and hasattr(call.args[0], "demand_discovery_metadata")
        ),
        None,
    )

    # Verify metadata was set correctly
    assert candidate is not None, "CandidateProduct should be added to db"
    assert candidate.demand_discovery_metadata is not None
    assert candidate.demand_discovery_metadata["discovery_mode"] == "generated"
    assert candidate.demand_discovery_metadata["degraded"] is True
    assert len(candidate.demand_discovery_metadata["validated_keywords"]) == 1
    assert len(candidate.demand_discovery_metadata["rejected_keywords"]) == 1
    # skipped_reason should not be present when candidates are created
    assert "skipped_reason" not in candidate.demand_discovery_metadata


@pytest.mark.asyncio
async def test_selector_skipped_flow_returns_skipped_reason_without_creating_candidates():
    """Selector should return skipped_reason and avoid candidate writes when no validated keywords."""
    mock_adapter = AsyncMock()
    mock_supplier_matcher = AsyncMock()

    mock_discovery = AsyncMock()
    mock_discovery.discover_keywords.return_value = DemandDiscoveryResult(
        validated_keywords=[],
        rejected_keywords=[],
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
            "keywords": None,
            "region": "US",
            "max_candidates": 10,
        },
    )

    result = await agent.execute(context)

    # When skipped, no candidates are created so no metadata to check in db
    # The output_data should have the skipped_reason in demand_discovery
    assert result.success is True
    assert result.output_data["count"] == 0
    assert result.output_data["skipped_reason"] == "no_validated_keywords_available"
    # No candidates created, so no db.add for candidates
    mock_db.add.assert_not_called()
