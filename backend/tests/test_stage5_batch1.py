"""Tests for Stage 5 first batch: PlatformRegistry and UnifiedListingService."""
import pytest
from decimal import Decimal
from uuid import uuid4

from app.core.enums import TargetPlatform, PlatformListingStatus, InventoryMode
from app.services.platform_registry import (
    PlatformRegistry,
    PlatformCapability,
    get_platform_registry,
)
from app.services.unified_listing_service import UnifiedListingService
from app.db.models import CandidateProduct, PlatformListing, ProductVariant


class TestPlatformRegistry:
    """Test PlatformRegistry functionality."""

    def test_registry_initialization(self):
        """Test that registry is initialized with platforms."""
        registry = get_platform_registry()

        # Check Temu is registered
        assert TargetPlatform.TEMU in registry.get_supported_platforms()

        # Check other platforms are registered (mock)
        assert TargetPlatform.AMAZON in registry.get_supported_platforms()
        assert TargetPlatform.OZON in registry.get_supported_platforms()

    def test_platform_capabilities(self):
        """Test platform capability checking."""
        registry = get_platform_registry()

        # Temu should have full capabilities
        assert registry.supports_feature(TargetPlatform.TEMU, PlatformCapability.CREATE_LISTING)
        assert registry.supports_feature(TargetPlatform.TEMU, PlatformCapability.UPDATE_LISTING)
        assert registry.supports_feature(TargetPlatform.TEMU, PlatformCapability.SYNC_INVENTORY)

        # Mock platforms should have limited capabilities
        assert registry.supports_feature(TargetPlatform.AMAZON, PlatformCapability.CREATE_LISTING)
        assert not registry.supports_feature(TargetPlatform.AMAZON, PlatformCapability.SYNC_INVENTORY)

    def test_get_adapter(self):
        """Test adapter resolution."""
        registry = get_platform_registry()

        # Get Temu adapter
        adapter = registry.get_adapter(TargetPlatform.TEMU, "us")
        assert adapter is not None
        assert adapter.platform == TargetPlatform.TEMU

        # Get mock adapter
        adapter = registry.get_adapter(TargetPlatform.AMAZON, "us")
        assert adapter is not None
        assert adapter.platform == TargetPlatform.AMAZON

    def test_adapter_caching(self):
        """Test that adapters are cached."""
        registry = get_platform_registry()

        adapter1 = registry.get_adapter(TargetPlatform.TEMU, "us")
        adapter2 = registry.get_adapter(TargetPlatform.TEMU, "us")

        # Should return same instance
        assert adapter1 is adapter2


class TestUnifiedListingService:
    """Test UnifiedListingService functionality."""

    @pytest.fixture
    def service(self):
        """Create UnifiedListingService instance."""
        return UnifiedListingService()

    @pytest.fixture
    async def sample_strategy_run(self, db_session):
        """Create sample strategy run."""
        from app.core.enums import TriggerType, StrategyRunStatus, SourcePlatform
        from app.db.models import StrategyRun

        strategy_run = StrategyRun(
            id=uuid4(),
            trigger_type=TriggerType.MANUAL,
            source_platform=SourcePlatform.TEMU,
            status=StrategyRunStatus.COMPLETED,
        )
        db_session.add(strategy_run)
        await db_session.commit()
        return strategy_run

    @pytest.fixture
    async def sample_candidate(self, db_session, sample_strategy_run):
        """Create sample candidate product."""
        from app.core.enums import SourcePlatform, CandidateStatus

        candidate = CandidateProduct(
            id=uuid4(),
            strategy_run_id=sample_strategy_run.id,
            source_platform=SourcePlatform.TEMU,
            title="Test Product",
            platform_price=Decimal("10.00"),
            category="Electronics",
            status=CandidateStatus.DISCOVERED,
        )
        db_session.add(candidate)
        await db_session.commit()
        return candidate

    @pytest.fixture
    async def sample_variant(self, db_session, sample_candidate):
        """Create sample product variant."""
        from app.db.models import ProductMaster
        from app.core.enums import ProductMasterStatus, ProductVariantStatus

        master = ProductMaster(
            id=uuid4(),
            candidate_product_id=sample_candidate.id,
            internal_sku=f"SKU-{uuid4().hex[:8].upper()}",
            name="Test Product",
            status=ProductMasterStatus.ACTIVE,
        )
        db_session.add(master)
        await db_session.flush()

        variant = ProductVariant(
            id=uuid4(),
            master_id=master.id,
            variant_sku=f"TEST-{uuid4().hex[:8].upper()}",
            inventory_mode=InventoryMode.PRE_ORDER,
            status=ProductVariantStatus.ACTIVE,
        )
        db_session.add(variant)
        await db_session.commit()
        return variant

    @pytest.fixture
    def mock_adapter_create_listing(self, service, monkeypatch):
        """Mock adapter create_listing to avoid API calls."""
        from app.services.platforms.base import PlatformListingData

        call_counter = [0]

        async def mock_create_listing(**kwargs):
            call_counter[0] += 1
            return PlatformListingData(
                platform_listing_id=f"TEST-MOCK-{call_counter[0]}",
                platform_url=f"https://example.com/item/{call_counter[0]}",
                status=PlatformListingStatus.PENDING,
            )

        # Mock for all adapters and regions
        for platform in [TargetPlatform.TEMU, TargetPlatform.AMAZON, TargetPlatform.OZON]:
            for region in ["us", "uk", "de", "fr", "jp", "au", "ca"]:
                try:
                    adapter = service.registry.get_adapter(platform, region)
                    monkeypatch.setattr(adapter, "create_listing", mock_create_listing)
                except:
                    pass

        return mock_create_listing

    async def test_create_listing(self, service, db_session, sample_candidate, sample_variant, mock_adapter_create_listing):
        """Test creating a listing via unified service."""
        payload = {
            "price": Decimal("25.00"),
            "currency": "USD",
            "inventory": 100,
            "title": "Test Product",
            "inventory_mode": InventoryMode.PRE_ORDER,
        }

        listing = await service.create_listing(
            db=db_session,
            platform=TargetPlatform.TEMU,
            region="us",
            marketplace=None,
            product_variant_id=sample_variant.id,
            candidate_product_id=sample_candidate.id,
            payload=payload,
        )

        assert listing is not None
        assert listing.platform == TargetPlatform.TEMU
        assert listing.region == "us"
        assert listing.price == Decimal("25.00")
        assert listing.currency == "USD"
        assert listing.inventory == 100
        assert listing.product_variant_id == sample_variant.id
        assert listing.candidate_product_id == sample_candidate.id

    async def test_get_sku_listings(self, service, db_session, sample_candidate, sample_variant, mock_adapter_create_listing):
        """Test querying listings by SKU."""
        # Create multiple listings for same SKU
        payload = {
            "price": Decimal("25.00"),
            "currency": "USD",
            "inventory": 100,
            "title": "Test Product",
            "inventory_mode": InventoryMode.PRE_ORDER,
        }

        listing1 = await service.create_listing(
            db=db_session,
            platform=TargetPlatform.TEMU,
            region="us",
            marketplace=None,
            product_variant_id=sample_variant.id,
            candidate_product_id=sample_candidate.id,
            payload=payload,
        )

        listing2 = await service.create_listing(
            db=db_session,
            platform=TargetPlatform.AMAZON,
            region="us",
            marketplace="amazon_us",
            product_variant_id=sample_variant.id,
            candidate_product_id=sample_candidate.id,
            payload=payload,
        )

        # Query listings by SKU
        listings = await service.get_sku_listings(
            db=db_session,
            product_variant_id=sample_variant.id,
        )

        assert len(listings) == 2
        platforms = {listing.platform for listing in listings}
        assert TargetPlatform.TEMU in platforms
        assert TargetPlatform.AMAZON in platforms

    async def test_get_listing_snapshot(self, service, db_session, sample_candidate, sample_variant, mock_adapter_create_listing):
        """Test getting listing snapshot."""
        payload = {
            "price": Decimal("25.00"),
            "currency": "USD",
            "inventory": 100,
            "title": "Test Product",
            "inventory_mode": InventoryMode.PRE_ORDER,
        }

        listing = await service.create_listing(
            db=db_session,
            platform=TargetPlatform.TEMU,
            region="us",
            marketplace=None,
            product_variant_id=sample_variant.id,
            candidate_product_id=sample_candidate.id,
            payload=payload,
        )

        snapshot = await service.get_listing_snapshot(
            db=db_session,
            listing_id=listing.id,
        )

        assert snapshot["listing_id"] == str(listing.id)
        assert snapshot["platform"] == "temu"
        assert snapshot["region"] == "us"
        assert snapshot["price"] == 25.00
        assert snapshot["currency"] == "USD"
        assert snapshot["inventory"] == 100
        assert snapshot["product_variant_id"] == str(sample_variant.id)

    async def test_get_platform_listings(self, service, db_session, sample_candidate, sample_variant, mock_adapter_create_listing):
        """Test querying listings by platform."""
        payload = {
            "price": Decimal("25.00"),
            "currency": "USD",
            "inventory": 100,
            "title": "Test Product",
            "inventory_mode": InventoryMode.PRE_ORDER,
        }

        # Create listings on different platforms
        await service.create_listing(
            db=db_session,
            platform=TargetPlatform.TEMU,
            region="us",
            marketplace=None,
            product_variant_id=sample_variant.id,
            candidate_product_id=sample_candidate.id,
            payload=payload,
        )

        await service.create_listing(
            db=db_session,
            platform=TargetPlatform.TEMU,
            region="uk",
            marketplace=None,
            product_variant_id=sample_variant.id,
            candidate_product_id=sample_candidate.id,
            payload=payload,
        )

        # Query Temu US listings
        listings = await service.get_platform_listings(
            db=db_session,
            platform=TargetPlatform.TEMU,
            region="us",
        )

        assert len(listings) >= 1
        assert all(listing.platform == TargetPlatform.TEMU for listing in listings)
        assert all(listing.region == "us" for listing in listings)


class TestPlatformListingModel:
    """Test PlatformListing model with multi-platform fields."""

    async def test_marketplace_field(self, db_session):
        """Test marketplace field on PlatformListing."""
        listing = PlatformListing(
            id=uuid4(),
            candidate_product_id=uuid4(),
            platform=TargetPlatform.AMAZON,
            region="us",
            marketplace="amazon_us",
            platform_listing_id="B08XYZ123",
            price=Decimal("29.99"),
            currency="USD",
            inventory=50,
            status=PlatformListingStatus.ACTIVE,
        )

        db_session.add(listing)
        await db_session.commit()

        # Verify marketplace field is persisted
        assert listing.marketplace == "amazon_us"

    async def test_composite_index_uniqueness(self, db_session):
        """Test composite index on platform + marketplace + platform_listing_id."""
        listing1 = PlatformListing(
            id=uuid4(),
            candidate_product_id=uuid4(),
            platform=TargetPlatform.AMAZON,
            region="us",
            marketplace="amazon_us",
            platform_listing_id="B08XYZ123",
            price=Decimal("29.99"),
            currency="USD",
            inventory=50,
            status=PlatformListingStatus.ACTIVE,
        )

        db_session.add(listing1)
        await db_session.commit()

        # Same platform_listing_id on different marketplace should be allowed
        listing2 = PlatformListing(
            id=uuid4(),
            candidate_product_id=uuid4(),
            platform=TargetPlatform.AMAZON,
            region="uk",
            marketplace="amazon_uk",
            platform_listing_id="B08XYZ123",  # Same ID, different marketplace
            price=Decimal("29.99"),
            currency="GBP",
            inventory=50,
            status=PlatformListingStatus.ACTIVE,
        )

        db_session.add(listing2)
        await db_session.commit()

        # Both should exist
        assert listing1.id != listing2.id
        assert listing1.marketplace != listing2.marketplace
