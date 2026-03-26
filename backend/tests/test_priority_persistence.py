"""Tests for persistence of priority_score and rank."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.agents.product_selector import ProductSelectorAgent
from app.agents.base.agent import AgentContext
from app.core.enums import SourcePlatform
from app.services.source_adapter import ProductData


@pytest.mark.asyncio
async def test_product_selector_persists_priority_score_and_rank():
    """Test that ProductSelectorAgent persists priority_score and rank."""
    # Mock source adapter with multiple products
    mock_adapter = AsyncMock()
    mock_products = [
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod1",
            source_url="https://temu.com/prod1",
            title="High Priority Product",
            category="electronics",
            currency="USD",
            platform_price=Decimal("49.99"),
            sales_count=5000,
            rating=Decimal("4.8"),
            main_image_url="https://example.com/image1.jpg",
            raw_payload={},
            normalized_attributes={},
            supplier_candidates=[],
        ),
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod2",
            source_url="https://temu.com/prod2",
            title="Medium Priority Product",
            category="electronics",
            currency="USD",
            platform_price=Decimal("29.99"),
            sales_count=1000,
            rating=Decimal("4.5"),
            main_image_url="https://example.com/image2.jpg",
            raw_payload={},
            normalized_attributes={},
            supplier_candidates=[],
        ),
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod3",
            source_url="https://temu.com/prod3",
            title="Low Priority Product",
            category="electronics",
            currency="USD",
            platform_price=Decimal("19.99"),
            sales_count=100,
            rating=Decimal("3.5"),
            main_image_url="https://example.com/image3.jpg",
            raw_payload={},
            normalized_attributes={},
            supplier_candidates=[],
        ),
    ]
    mock_adapter.fetch_products.return_value = mock_products

    # Mock supplier matcher
    mock_supplier_matcher = AsyncMock()
    mock_supplier_matcher.find_suppliers.return_value = []

    # Mock database
    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    # Create agent
    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        enable_demand_validation=False,
        enable_seasonal_boost=True,
    )

    # Create context
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "temu",
            "category": "electronics",
            "keywords": ["electronics"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    # Mock seasonal calendar
    with patch("app.agents.product_selector.get_seasonal_calendar") as mock_calendar:
        mock_calendar_instance = MagicMock()
        mock_calendar_instance.get_boost_factor.return_value = 1.5
        mock_calendar.return_value = mock_calendar_instance

        # Execute agent
        result = await agent.execute(context)

    # Verify success
    assert result.success is True
    assert result.output_data["count"] == 3

    # Verify all candidates were added
    assert mock_db.add.call_count == 3  # 3 candidates, no suppliers

    # Get candidates from add calls
    candidates = [call[0][0] for call in mock_db.add.call_args_list]

    # Verify each candidate has priority_score and priority_rank
    for i, candidate in enumerate(candidates, start=1):
        assert "priority_score" in candidate.normalized_attributes
        assert "priority_rank" in candidate.normalized_attributes
        assert "seasonal_boost" in candidate.normalized_attributes

        # Verify values are valid
        assert isinstance(candidate.normalized_attributes["priority_score"], float)
        assert candidate.normalized_attributes["priority_score"] >= 0.0
        assert candidate.normalized_attributes["priority_rank"] == i
        assert candidate.normalized_attributes["seasonal_boost"] == 1.5

    # Verify ranking order (first candidate should have highest score)
    assert candidates[0].normalized_attributes["priority_rank"] == 1
    assert candidates[1].normalized_attributes["priority_rank"] == 2
    assert candidates[2].normalized_attributes["priority_rank"] == 3

    # Verify scores are in descending order
    assert (
        candidates[0].normalized_attributes["priority_score"]
        >= candidates[1].normalized_attributes["priority_score"]
        >= candidates[2].normalized_attributes["priority_score"]
    )


@pytest.mark.asyncio
async def test_product_selector_persists_without_seasonal_boost():
    """Test that priority_score and rank are still persisted when seasonal boost is disabled."""
    # Mock source adapter
    mock_adapter = AsyncMock()
    mock_products = [
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod1",
            source_url="https://temu.com/prod1",
            title="Product A",
            category="electronics",
            currency="USD",
            platform_price=Decimal("29.99"),
            sales_count=1000,
            rating=Decimal("4.5"),
            main_image_url="https://example.com/image1.jpg",
            raw_payload={},
            normalized_attributes={},
            supplier_candidates=[],
        )
    ]
    mock_adapter.fetch_products.return_value = mock_products

    # Mock supplier matcher
    mock_supplier_matcher = AsyncMock()
    mock_supplier_matcher.find_suppliers.return_value = []

    # Mock database
    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    # Create agent with seasonal boost disabled
    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        enable_demand_validation=False,
        enable_seasonal_boost=False,
    )

    # Create context
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "temu",
            "category": "electronics",
            "keywords": ["electronics"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    # Execute agent
    result = await agent.execute(context)

    # Verify success
    assert result.success is True

    # Get candidate
    candidate = mock_db.add.call_args_list[0][0][0]

    # When seasonal boost is disabled, priority_score/rank are not persisted
    assert "priority_score" not in candidate.normalized_attributes
    assert "priority_rank" not in candidate.normalized_attributes
    assert "seasonal_boost" not in candidate.normalized_attributes


@pytest.mark.asyncio
async def test_product_selector_priority_rank_matches_sort_order():
    """Test that priority_rank matches the actual sort order."""
    # Mock source adapter with products in unsorted order
    mock_adapter = AsyncMock()
    mock_products = [
        # Low score product (comes first in input)
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="low",
            source_url="https://temu.com/low",
            title="Low Score Product",
            category="electronics",
            currency="USD",
            platform_price=Decimal("19.99"),
            sales_count=10,
            rating=Decimal("3.0"),
            main_image_url="https://example.com/image1.jpg",
            raw_payload={},
            normalized_attributes={},
            supplier_candidates=[],
        ),
        # High score product (comes second in input)
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="high",
            source_url="https://temu.com/high",
            title="High Score Product",
            category="electronics",
            currency="USD",
            platform_price=Decimal("49.99"),
            sales_count=10000,
            rating=Decimal("4.9"),
            main_image_url="https://example.com/image2.jpg",
            raw_payload={},
            normalized_attributes={},
            supplier_candidates=[],
        ),
    ]
    mock_adapter.fetch_products.return_value = mock_products

    # Mock supplier matcher
    mock_supplier_matcher = AsyncMock()
    mock_supplier_matcher.find_suppliers.return_value = []

    # Mock database
    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    # Create agent
    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        enable_demand_validation=False,
        enable_seasonal_boost=True,
    )

    # Create context
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "temu",
            "category": "electronics",
            "keywords": ["electronics"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    # Mock seasonal calendar
    with patch("app.agents.product_selector.get_seasonal_calendar") as mock_calendar:
        mock_calendar_instance = MagicMock()
        mock_calendar_instance.get_boost_factor.return_value = 1.5
        mock_calendar.return_value = mock_calendar_instance

        # Execute agent
        result = await agent.execute(context)

    # Verify success
    assert result.success is True

    # Get candidates in the order they were added
    candidates = [call[0][0] for call in mock_db.add.call_args_list]

    # The high score product should be ranked first, despite being second in input
    assert candidates[0].source_product_id == "high"
    assert candidates[0].normalized_attributes["priority_rank"] == 1

    assert candidates[1].source_product_id == "low"
    assert candidates[1].normalized_attributes["priority_rank"] == 2
