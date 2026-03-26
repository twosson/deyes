"""Tests for seasonal boost integration in ProductSelectorAgent."""
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.agents.product_selector import ProductSelectorAgent
from app.agents.base.agent import AgentContext
from app.core.enums import SourcePlatform
from app.services.source_adapter import ProductData


@pytest.mark.asyncio
async def test_product_selector_applies_seasonal_boost():
    """Test that ProductSelectorAgent applies seasonal boost."""
    # Mock source adapter
    mock_adapter = AsyncMock()
    mock_products = [
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod1",
            source_url="https://temu.com/prod1",
            title="Wireless Earbuds",
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

    # Create agent with seasonal boost enabled
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
            "keywords": ["wireless earbuds"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    # Mock seasonal calendar to return specific boost
    with patch("app.agents.product_selector.get_seasonal_calendar") as mock_calendar:
        mock_calendar_instance = MagicMock()
        mock_calendar_instance.get_boost_factor.return_value = 1.5
        mock_calendar.return_value = mock_calendar_instance

        # Execute agent
        result = await agent.execute(context)

    # Verify seasonal boost was applied
    assert result.success is True
    mock_calendar.assert_called_once_with(lookahead_days=90)
    mock_calendar_instance.get_boost_factor.assert_called_once_with(category="electronics")

    # Verify product was created with seasonal boost in normalized_attributes
    assert mock_db.add.called
    # Get the candidate product from the first add call
    candidate = mock_db.add.call_args_list[0][0][0]
    assert "seasonal_boost" in candidate.normalized_attributes
    assert candidate.normalized_attributes["seasonal_boost"] == 1.5


@pytest.mark.asyncio
async def test_product_selector_seasonal_boost_disabled():
    """Test that seasonal boost can be disabled."""
    # Mock source adapter
    mock_adapter = AsyncMock()
    mock_products = [
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod1",
            source_url="https://temu.com/prod1",
            title="Wireless Earbuds",
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
            "keywords": ["wireless earbuds"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    # Execute agent
    result = await agent.execute(context)

    # Verify seasonal boost was NOT applied
    assert result.success is True

    # Verify product was created without seasonal boost
    assert mock_db.add.called
    candidate = mock_db.add.call_args_list[0][0][0]
    assert "seasonal_boost" not in candidate.normalized_attributes


@pytest.mark.asyncio
async def test_product_selector_seasonal_boost_no_category():
    """Test that seasonal boost handles missing category gracefully."""
    # Mock source adapter
    mock_adapter = AsyncMock()
    mock_products = [
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod1",
            source_url="https://temu.com/prod1",
            title="Generic Product",
            category=None,  # No category
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

    # Create agent with seasonal boost enabled
    agent = ProductSelectorAgent(
        source_adapter=mock_adapter,
        supplier_matcher=mock_supplier_matcher,
        enable_demand_validation=False,
        enable_seasonal_boost=True,
    )

    # Create context (no category)
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=mock_db,
        input_data={
            "platform": "temu",
            "keywords": ["generic product"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    # Execute agent
    result = await agent.execute(context)

    # Should succeed without seasonal boost
    assert result.success is True

    # Verify product was created without seasonal boost
    assert mock_db.add.called
    candidate = mock_db.add.call_args_list[0][0][0]
    assert "seasonal_boost" not in candidate.normalized_attributes


@pytest.mark.asyncio
async def test_product_selector_christmas_electronics_boost():
    """Test realistic scenario: electronics boost before Christmas."""
    # Mock source adapter
    mock_adapter = AsyncMock()
    mock_products = [
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod1",
            source_url="https://temu.com/prod1",
            title="Wireless Headphones",
            category="electronics",
            currency="USD",
            platform_price=Decimal("49.99"),
            sales_count=5000,
            rating=Decimal("4.7"),
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
            "keywords": ["wireless headphones"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    # Mock seasonal calendar with realistic Christmas boost
    with patch("app.agents.product_selector.get_seasonal_calendar") as mock_calendar:
        mock_calendar_instance = MagicMock()
        # Realistic boost for electronics before Christmas (Black Friday + Christmas)
        mock_calendar_instance.get_boost_factor.return_value = 1.55
        mock_calendar.return_value = mock_calendar_instance

        # Execute agent
        result = await agent.execute(context)

    # Verify high seasonal boost was applied
    assert result.success is True
    candidate = mock_db.add.call_args_list[0][0][0]
    assert candidate.normalized_attributes["seasonal_boost"] == 1.55


@pytest.mark.asyncio
async def test_product_selector_valentines_jewelry_boost():
    """Test realistic scenario: jewelry boost before Valentine's Day."""
    # Mock source adapter
    mock_adapter = AsyncMock()
    mock_products = [
        ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id="prod1",
            source_url="https://temu.com/prod1",
            title="Silver Necklace",
            category="jewelry",
            currency="USD",
            platform_price=Decimal("39.99"),
            sales_count=2000,
            rating=Decimal("4.6"),
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
            "category": "jewelry",
            "keywords": ["silver necklace"],
            "region": "US",
            "max_candidates": 10,
        },
    )

    # Mock seasonal calendar with Valentine's boost
    with patch("app.agents.product_selector.get_seasonal_calendar") as mock_calendar:
        mock_calendar_instance = MagicMock()
        # Realistic boost for jewelry before Valentine's Day
        mock_calendar_instance.get_boost_factor.return_value = 1.45
        mock_calendar.return_value = mock_calendar_instance

        # Execute agent
        result = await agent.execute(context)

    # Verify seasonal boost was applied
    assert result.success is True
    candidate = mock_db.add.call_args_list[0][0][0]
    assert candidate.normalized_attributes["seasonal_boost"] == 1.45
