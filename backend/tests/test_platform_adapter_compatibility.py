"""Platform adapter compatibility tests.

Tests backward compatibility of platform adapter interface changes,
focusing on TemuAdapter category resolution and MockPlatformAdapter parameter handling.
"""
import pytest
from decimal import Decimal
from uuid import uuid4

from app.core.enums import (
    AssetType,
    CandidateStatus,
    PlatformListingStatus,
    SourcePlatform,
    TargetPlatform,
)
from app.db.models import CandidateProduct, ContentAsset
from app.services.platforms.base import MockPlatformAdapter
from app.services.platforms.temu import TemuAdapter


# Fixtures

@pytest.fixture
def mock_strategy_run_id():
    """Strategy run ID shared across test fixtures."""
    return uuid4()


@pytest.fixture
def mock_product(mock_strategy_run_id):
    """Create a mock CandidateProduct for testing.

    CandidateProduct requires: id, strategy_run_id, source_platform, status, title.
    """
    return CandidateProduct(
        id=uuid4(),
        strategy_run_id=mock_strategy_run_id,
        source_platform=SourcePlatform.TEMU,
        title="Test Product",
        category="electronics",
        status=CandidateStatus.DISCOVERED,
        raw_payload={},
    )


@pytest.fixture
def mock_assets(mock_strategy_run_id, mock_product):
    """Create mock ContentAssets for testing.

    ContentAsset requires: id, candidate_product_id, asset_type, file_url.
    """
    candidate_id = mock_product.id
    return [
        ContentAsset(
            id=uuid4(),
            candidate_product_id=candidate_id,
            asset_type=AssetType.MAIN_IMAGE,
            file_url="https://example.com/image1.jpg",
        ),
        ContentAsset(
            id=uuid4(),
            candidate_product_id=candidate_id,
            asset_type=AssetType.MAIN_IMAGE,
            file_url="https://example.com/image2.jpg",
        ),
    ]


@pytest.fixture
def temu_adapter():
    """Create a TemuAdapter instance for testing."""
    return TemuAdapter(
        app_key="test_key",
        app_secret="test_secret",
        region="us",
    )


# TemuAdapter category resolution tests

class TestTemuAdapterCategoryResolution:
    """Test TemuAdapter._resolve_temu_category_id() priority logic."""

    def test_explicit_category_id_takes_priority(self, temu_adapter):
        """Explicit category_id should take priority over all other sources."""
        result = temu_adapter._resolve_temu_category_id(
            category_id=9999,
            category="electronics",
            product_category="home gadgets",
        )
        assert result == 9999

    def test_explicit_category_id_string_conversion(self, temu_adapter):
        """Explicit category_id as string should be converted to int."""
        result = temu_adapter._resolve_temu_category_id(
            category_id="8888",
            category="electronics",
            product_category="home gadgets",
        )
        assert result == 8888

    def test_invalid_category_id_falls_back_to_mapping(self, temu_adapter):
        """Invalid category_id should fall back to CATEGORY_MAPPING."""
        result = temu_adapter._resolve_temu_category_id(
            category_id="invalid",
            category="electronics",
            product_category="home gadgets",
        )
        # Should fall back to category="electronics" -> 5001
        assert result == 5001

    def test_category_mapping_fallback(self, temu_adapter):
        """Without category_id, should use category + CATEGORY_MAPPING."""
        result = temu_adapter._resolve_temu_category_id(
            category_id=None,
            category="phone accessories",
            product_category="electronics",
        )
        # "phone accessories" -> 1001
        assert result == 1001

    def test_product_category_fallback(self, temu_adapter):
        """Without category_id or category, should use product_category."""
        result = temu_adapter._resolve_temu_category_id(
            category_id=None,
            category=None,
            product_category="beauty tools",
        )
        # "beauty tools" -> 3001
        assert result == 3001

    def test_default_category_when_no_match(self, temu_adapter):
        """Should return 0 when no category matches."""
        result = temu_adapter._resolve_temu_category_id(
            category_id=None,
            category="unknown category",
            product_category=None,
        )
        assert result == 0

    def test_case_insensitive_category_mapping(self, temu_adapter):
        """Category mapping should be case-insensitive."""
        result = temu_adapter._resolve_temu_category_id(
            category_id=None,
            category="ELECTRONICS",
            product_category=None,
        )
        # "ELECTRONICS" -> "electronics" -> 5001
        assert result == 5001


# MockPlatformAdapter compatibility tests

class TestMockPlatformAdapterCompatibility:
    """Test MockPlatformAdapter accepts new parameters without breaking."""

    @pytest.mark.asyncio
    async def test_accepts_new_category_id_param(self, mock_product, mock_assets):
        """MockPlatformAdapter should accept category_id parameter."""
        adapter = MockPlatformAdapter(TargetPlatform.TEMU)

        result = await adapter.create_listing(
            product=mock_product,
            assets=mock_assets,
            region="us",
            price=Decimal("19.99"),
            currency="USD",
            inventory=100,
            category_id=1234,
        )

        assert result.platform_listing_id.startswith("MOCK-")
        assert result.status == PlatformListingStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_accepts_new_category_name_param(self, mock_product, mock_assets):
        """MockPlatformAdapter should accept category_name parameter."""
        adapter = MockPlatformAdapter(TargetPlatform.AMAZON)

        result = await adapter.create_listing(
            product=mock_product,
            assets=mock_assets,
            region="us",
            price=Decimal("29.99"),
            currency="USD",
            inventory=50,
            category_name="Electronics > Accessories",
        )

        assert result.platform_listing_id.startswith("MOCK-")
        assert result.status == PlatformListingStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_accepts_new_platform_context_param(self, mock_product, mock_assets):
        """MockPlatformAdapter should accept platform_context parameter."""
        adapter = MockPlatformAdapter(TargetPlatform.OZON)

        result = await adapter.create_listing(
            product=mock_product,
            assets=mock_assets,
            region="ru",
            price=Decimal("39.99"),
            currency="RUB",
            inventory=75,
            platform_context={"warehouse_id": "W123", "shipping_template": "standard"},
        )

        assert result.platform_listing_id.startswith("MOCK-")
        assert result.status == PlatformListingStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_accepts_all_new_params_together(self, mock_product, mock_assets):
        """MockPlatformAdapter should accept all new parameters together."""
        adapter = MockPlatformAdapter(TargetPlatform.TEMU)

        result = await adapter.create_listing(
            product=mock_product,
            assets=mock_assets,
            region="us",
            price=Decimal("49.99"),
            currency="USD",
            inventory=200,
            category_id=5001,
            category_name="Electronics",
            platform_context={"priority": "high"},
        )

        assert result.platform_listing_id.startswith("MOCK-")
        assert result.status == PlatformListingStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_mock_behavior_unchanged_by_new_params(self, mock_product, mock_assets):
        """New parameters should not affect MockPlatformAdapter's core behavior."""
        adapter = MockPlatformAdapter(TargetPlatform.TEMU)

        # Create listing with new params
        result = await adapter.create_listing(
            product=mock_product,
            assets=mock_assets,
            region="us",
            price=Decimal("19.99"),
            currency="USD",
            inventory=100,
            category_id=1234,
            category_name="Test Category",
            platform_context={"test": "data"},
        )

        listing_id = result.platform_listing_id

        # Verify listing was stored correctly
        status = await adapter.get_listing_status(platform_listing_id=listing_id)
        assert status["product_id"] == str(mock_product.id)
        assert status["price"] == 19.99
        assert status["inventory"] == 100

        # Verify update still works
        update_success = await adapter.update_listing(
            platform_listing_id=listing_id,
            price=Decimal("24.99"),
        )
        assert update_success is True

        # Verify updated price
        updated_status = await adapter.get_listing_status(platform_listing_id=listing_id)
        assert updated_status["price"] == 24.99


# Backward compatibility tests

class TestBackwardCompatibility:
    """Test that old code without new parameters still works."""

    @pytest.mark.asyncio
    async def test_create_listing_without_new_params(self, mock_product, mock_assets):
        """Old create_listing calls without new params should still work."""
        adapter = MockPlatformAdapter(TargetPlatform.TEMU)

        # Old-style call without category_id, category_name, platform_context
        result = await adapter.create_listing(
            product=mock_product,
            assets=mock_assets,
            region="us",
            price=Decimal("19.99"),
            currency="USD",
            inventory=100,
        )

        assert result.platform_listing_id.startswith("MOCK-")
        assert result.status == PlatformListingStatus.ACTIVE

    def test_temu_resolve_without_category_id(self, temu_adapter):
        """TemuAdapter should work without category_id parameter."""
        # Old-style call without category_id
        result = temu_adapter._resolve_temu_category_id(
            category_id=None,
            category="electronics",
            product_category="home gadgets",
        )
        assert result == 5001
