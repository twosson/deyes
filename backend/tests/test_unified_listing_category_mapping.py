"""Tests for UnifiedListingService category mapping integration."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CandidateStatus, SourcePlatform, StrategyRunStatus, TargetPlatform, TriggerType
from app.db.models import CandidateProduct, PlatformCategoryMapping, StrategyRun
from app.services.platforms.temu import TemuAdapterMock
from app.services.unified_listing_service import UnifiedListingService


@pytest.fixture
def service() -> UnifiedListingService:
    """Create UnifiedListingService instance."""
    return UnifiedListingService()


@pytest.fixture
async def sample_strategy_run(db_session: AsyncSession) -> StrategyRun:
    """Create sample strategy run."""
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
async def sample_candidate(db_session: AsyncSession, sample_strategy_run: StrategyRun) -> CandidateProduct:
    """Create sample candidate product."""
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=sample_strategy_run.id,
        source_platform=SourcePlatform.TEMU,
        title="Test Product",
        category="electronics",
        platform_price=Decimal("25.00"),
        status=CandidateStatus.COPY_GENERATED,
    )
    db_session.add(candidate)
    await db_session.commit()
    return candidate


@pytest.mark.asyncio
async def test_resolve_platform_category_with_policy_mapping(
    service: UnifiedListingService,
    db_session: AsyncSession,
):
    """UnifiedListingService should resolve category mapping from policy."""
    # Insert category mapping
    mapping = PlatformCategoryMapping(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="us",
        internal_category="electronics",
        platform_category_id="5001",
        platform_category_name="Consumer Electronics",
        mapping_version=1,
        is_active=True,
    )
    db_session.add(mapping)
    await db_session.commit()

    # Resolve category
    result = await service._resolve_platform_category(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
        category="electronics",
    )

    assert result["category"] == "electronics"
    assert result["category_id"] == "5001"
    assert result["category_name"] == "Consumer Electronics"
    assert result["mapping_source"] == "policy"


@pytest.mark.asyncio
async def test_resolve_platform_category_fallback_without_mapping(
    service: UnifiedListingService,
    db_session: AsyncSession,
):
    """UnifiedListingService should fallback to original category when no mapping exists."""
    # No mapping in DB
    result = await service._resolve_platform_category(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
        category="unknown_category",
    )

    assert result["category"] == "unknown_category"
    assert result["category_id"] is None
    assert result["category_name"] is None
    assert result["mapping_source"] == "fallback"


@pytest.mark.asyncio
async def test_resolve_platform_category_passthrough_when_no_category(
    service: UnifiedListingService,
    db_session: AsyncSession,
):
    """UnifiedListingService should passthrough when category is None."""
    result = await service._resolve_platform_category(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
        category=None,
    )

    assert result["category"] is None
    assert result["category_id"] is None
    assert result["category_name"] is None
    assert result["mapping_source"] == "passthrough"


@pytest.mark.asyncio
async def test_resolve_platform_category_prefers_region_specific_mapping(
    service: UnifiedListingService,
    db_session: AsyncSession,
):
    """UnifiedListingService should prefer region-specific mapping over platform-wide mapping."""
    # Platform-wide mapping
    platform_mapping = PlatformCategoryMapping(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region=None,
        internal_category="beauty tools",
        platform_category_id="3000",
        platform_category_name="Beauty",
        mapping_version=1,
        is_active=True,
    )
    db_session.add(platform_mapping)

    # Region-specific mapping
    region_mapping = PlatformCategoryMapping(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        internal_category="beauty tools",
        platform_category_id="3001",
        platform_category_name="Beauty UK",
        mapping_version=1,
        is_active=True,
    )
    db_session.add(region_mapping)
    await db_session.commit()

    result = await service._resolve_platform_category(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="uk",
        category="beauty tools",
    )

    assert result["category_id"] == "3001"
    assert result["category_name"] == "Beauty UK"
    assert result["mapping_source"] == "policy"


@pytest.mark.asyncio
async def test_create_listing_passes_category_id_to_adapter_when_mapping_exists(
    service: UnifiedListingService,
    db_session: AsyncSession,
    sample_candidate: CandidateProduct,
    monkeypatch,
):
    """create_listing should pass resolved category_id to adapter when mapping exists."""
    # Insert category mapping
    mapping = PlatformCategoryMapping(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="us",
        internal_category="electronics",
        platform_category_id="5001",
        platform_category_name="Consumer Electronics",
        mapping_version=1,
        is_active=True,
    )
    db_session.add(mapping)
    await db_session.commit()

    # Mock adapter to capture arguments
    captured = {}

    async def mock_create_listing(**kwargs):
        captured.update(kwargs)
        from app.services.platforms.base import PlatformListingData
        return PlatformListingData(
            platform_listing_id="TEST-123",
            platform_url="https://example.com/listing/TEST-123",
        )

    adapter = service.registry.get_adapter(TargetPlatform.TEMU, "us")
    monkeypatch.setattr(adapter, "create_listing", mock_create_listing)

    # Create listing
    await service.create_listing(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
        marketplace=None,
        product_variant_id=None,
        candidate_product_id=sample_candidate.id,
        payload={
            "price": Decimal("25.00"),
            "currency": "USD",
            "inventory": 100,
            "title": "Test Product",
            "description": "Test Description",
            "category": "electronics",
            "assets": [],
        },
    )

    # Verify category_id was passed to adapter
    assert captured["category"] == "electronics"
    assert captured["category_id"] == "5001"
    assert captured["category_name"] == "Consumer Electronics"


@pytest.mark.asyncio
async def test_temu_adapter_uses_explicit_category_id_priority():
    """TemuAdapter should prioritize explicit category_id over hardcoded mapping."""
    adapter = TemuAdapterMock(region="us")

    # Explicit category_id should win over hardcoded mapping
    result = adapter._resolve_temu_category_id(
        category_id="9999",
        category="electronics",  # Would map to 5001 via hardcoded mapping
        product_category="beauty",  # Would map to 0 via hardcoded mapping
    )

    assert result == 9999


@pytest.mark.asyncio
async def test_temu_adapter_fallbacks_to_hardcoded_mapping_when_no_category_id():
    """TemuAdapter should fallback to hardcoded mapping when no explicit category_id."""
    adapter = TemuAdapterMock(region="us")

    # No category_id, should use hardcoded mapping from category
    result = adapter._resolve_temu_category_id(
        category_id=None,
        category="electronics",
        product_category="beauty",
    )

    assert result == 5001  # electronics -> 5001

    # No category, should fallback to product_category
    result = adapter._resolve_temu_category_id(
        category_id=None,
        category=None,
        product_category="sports",
    )

    assert result == 8001  # sports -> 8001


@pytest.mark.asyncio
async def test_temu_adapter_handles_invalid_category_id_gracefully():
    """TemuAdapter should handle invalid category_id gracefully and fallback."""
    adapter = TemuAdapterMock(region="us")

    # Invalid category_id should fallback to hardcoded mapping
    result = adapter._resolve_temu_category_id(
        category_id="invalid",
        category="electronics",
        product_category="beauty",
    )

    assert result == 5001  # Falls back to electronics hardcoded mapping

    # Invalid category_id and no valid category should return 0
    result = adapter._resolve_temu_category_id(
        category_id="invalid",
        category="unknown_category",
        product_category="unknown_category",
    )

    assert result == 0
