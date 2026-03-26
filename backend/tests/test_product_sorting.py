"""Tests for candidate product sorting with seasonal boost."""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from app.agents.product_selector import ProductSelectorAgent
from app.core.enums import SourcePlatform
from app.services.source_adapter import ProductData


class MockValidationResult:
    """Mock validation result for testing."""

    def __init__(self, keyword: str, competition_density: str):
        self.keyword = keyword
        self.competition_density = MagicMock()
        self.competition_density.value = competition_density


class TestProductSorting:
    """Test product sorting by priority score."""

    def test_sort_by_seasonal_boost_only(self):
        """Test sorting when only seasonal boost differs."""
        agent = ProductSelectorAgent(enable_demand_validation=False)

        # Create products with same sales/rating but different seasonal contexts
        products = [
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
            ),
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="prod2",
                source_url="https://temu.com/prod2",
                title="Bluetooth Speaker",
                category="electronics",
                currency="USD",
                platform_price=Decimal("39.99"),
                sales_count=1000,
                rating=Decimal("4.5"),
                main_image_url="https://example.com/image2.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
        ]

        # Same seasonal boost for all products in category
        sorted_products_with_scores = agent._sort_products_by_priority(
            products=products,
            seasonal_boost=1.5,
            validation_results=[],
        )

        # Extract products from tuples
        sorted_products = [p for p, score in sorted_products_with_scores]

        # With same scores, original order should be preserved (stable sort)
        assert sorted_products[0].source_product_id == "prod1"
        assert sorted_products[1].source_product_id == "prod2"

    def test_sort_by_sales_count(self):
        """Test sorting prioritizes higher sales count."""
        agent = ProductSelectorAgent(enable_demand_validation=False)

        products = [
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="low_sales",
                source_url="https://temu.com/low_sales",
                title="Product A",
                category="electronics",
                currency="USD",
                platform_price=Decimal("29.99"),
                sales_count=100,
                rating=Decimal("4.5"),
                main_image_url="https://example.com/image1.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="high_sales",
                source_url="https://temu.com/high_sales",
                title="Product B",
                category="electronics",
                currency="USD",
                platform_price=Decimal("29.99"),
                sales_count=5000,
                rating=Decimal("4.5"),
                main_image_url="https://example.com/image2.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
        ]

        sorted_products_with_scores = agent._sort_products_by_priority(
            products=products,
            seasonal_boost=1.0,
            validation_results=[],
        )

        # Extract products from tuples
        sorted_products = [p for p, score in sorted_products_with_scores]

        # Higher sales should rank first
        assert sorted_products[0].source_product_id == "high_sales"
        assert sorted_products[1].source_product_id == "low_sales"

    def test_sort_by_rating(self):
        """Test sorting prioritizes higher rating."""
        agent = ProductSelectorAgent(enable_demand_validation=False)

        products = [
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="low_rating",
                source_url="https://temu.com/low_rating",
                title="Product A",
                category="electronics",
                currency="USD",
                platform_price=Decimal("29.99"),
                sales_count=1000,
                rating=Decimal("3.5"),
                main_image_url="https://example.com/image1.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="high_rating",
                source_url="https://temu.com/high_rating",
                title="Product B",
                category="electronics",
                currency="USD",
                platform_price=Decimal("29.99"),
                sales_count=1000,
                rating=Decimal("4.8"),
                main_image_url="https://example.com/image2.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
        ]

        sorted_products_with_scores = agent._sort_products_by_priority(
            products=products,
            seasonal_boost=1.0,
            validation_results=[],
        )

        sorted_products = [p for p, score in sorted_products_with_scores]

        # Higher rating should rank first
        assert sorted_products[0].source_product_id == "high_rating"
        assert sorted_products[1].source_product_id == "low_rating"

    def test_sort_by_competition_density(self):
        """Test sorting prioritizes lower competition density."""
        agent = ProductSelectorAgent(enable_demand_validation=True)

        products = [
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="high_comp",
                source_url="https://temu.com/high_comp",
                title="Phone Case",
                category="electronics",
                currency="USD",
                platform_price=Decimal("19.99"),
                sales_count=1000,
                rating=Decimal("4.5"),
                main_image_url="https://example.com/image1.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="low_comp",
                source_url="https://temu.com/low_comp",
                title="Waterproof Wireless Phone Charger for Car",
                category="electronics",
                currency="USD",
                platform_price=Decimal("39.99"),
                sales_count=1000,
                rating=Decimal("4.5"),
                main_image_url="https://example.com/image2.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
        ]

        validation_results = [
            MockValidationResult("phone case", "high"),
            MockValidationResult("waterproof wireless phone charger for car", "low"),
        ]

        sorted_products_with_scores = agent._sort_products_by_priority(
            products=products,
            seasonal_boost=1.0,
            validation_results=validation_results,
        )

        sorted_products = [p for p, score in sorted_products_with_scores]

        # Lower competition should rank first
        assert sorted_products[0].source_product_id == "low_comp"
        assert sorted_products[1].source_product_id == "high_comp"

    def test_sort_by_combined_factors(self):
        """Test sorting with combined factors."""
        agent = ProductSelectorAgent(enable_demand_validation=True)

        products = [
            # High sales, low rating, high competition
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="prod_a",
                source_url="https://temu.com/prod_a",
                title="Phone Case",
                category="electronics",
                currency="USD",
                platform_price=Decimal("19.99"),
                sales_count=10000,
                rating=Decimal("3.5"),
                main_image_url="https://example.com/image1.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
            # Medium sales, high rating, low competition
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="prod_b",
                source_url="https://temu.com/prod_b",
                title="Waterproof Wireless Phone Charger for Car",
                category="electronics",
                currency="USD",
                platform_price=Decimal("39.99"),
                sales_count=1000,
                rating=Decimal("4.8"),
                main_image_url="https://example.com/image2.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
            # Low sales, high rating, low competition
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="prod_c",
                source_url="https://temu.com/prod_c",
                title="Bluetooth Speaker",
                category="electronics",
                currency="USD",
                platform_price=Decimal("49.99"),
                sales_count=100,
                rating=Decimal("4.9"),
                main_image_url="https://example.com/image3.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
        ]

        validation_results = [
            MockValidationResult("phone case", "high"),
            MockValidationResult("waterproof wireless phone charger for car", "low"),
            MockValidationResult("bluetooth speaker", "medium"),
        ]

        # Apply seasonal boost (e.g., before Black Friday)
        sorted_products_with_scores = agent._sort_products_by_priority(
            products=products,
            seasonal_boost=1.5,
            validation_results=validation_results,
        )

        sorted_products = [p for p, score in sorted_products_with_scores]

        # Product B should likely rank first due to good balance of factors
        # Product A has high sales but high competition and low rating
        # Product C has low sales
        assert sorted_products[0].source_product_id in ["prod_a", "prod_b"]
        assert len(sorted_products) == 3

    def test_sort_handles_missing_data(self):
        """Test sorting handles missing sales/rating gracefully."""
        agent = ProductSelectorAgent(enable_demand_validation=False)

        products = [
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="missing_data",
                source_url="https://temu.com/missing_data",
                title="Product A",
                category="electronics",
                currency="USD",
                platform_price=Decimal("29.99"),
                sales_count=None,
                rating=None,
                main_image_url="https://example.com/image1.jpg",
                raw_payload={},
                normalized_attributes={},
                supplier_candidates=[],
            ),
            ProductData(
                source_platform=SourcePlatform.TEMU,
                source_product_id="complete_data",
                source_url="https://temu.com/complete_data",
                title="Product B",
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
        ]

        sorted_products_with_scores = agent._sort_products_by_priority(
            products=products,
            seasonal_boost=1.0,
            validation_results=[],
        )

        sorted_products = [p for p, score in sorted_products_with_scores]

        # Complete data should rank first
        assert sorted_products[0].source_product_id == "complete_data"
        assert sorted_products[1].source_product_id == "missing_data"

    def test_sort_seasonal_boost_influence(self):
        """Test that higher seasonal boost increases priority score."""
        agent = ProductSelectorAgent(enable_demand_validation=False)

        products = [
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
            ),
        ]

        # Test score calculation indirectly by comparing sort behavior
        sorted_low_boost = agent._sort_products_by_priority(
            products=products.copy(),
            seasonal_boost=1.0,
            validation_results=[],
        )

        sorted_high_boost = agent._sort_products_by_priority(
            products=products.copy(),
            seasonal_boost=1.6,
            validation_results=[],
        )

        # Same product, but we can verify the method runs without error
        assert len(sorted_low_boost) == 1
        assert len(sorted_high_boost) == 1
        assert sorted_low_boost[0][0].source_product_id == "prod1"
        assert sorted_high_boost[0][0].source_product_id == "prod1"

        # Verify scores are different
        low_score = sorted_low_boost[0][1]
        high_score = sorted_high_boost[0][1]
        assert high_score > low_score  # Higher seasonal boost should give higher score
