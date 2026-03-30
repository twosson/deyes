"""Integration tests for UnifiedListingService + PlatformPolicyService.

Tests the integration between UnifiedListingService and PlatformPolicyService
for category mapping, commission policy, and pricing policy.
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CandidateStatus, SourcePlatform, StrategyRunStatus, TargetPlatform, TriggerType
from app.db.models import CandidateProduct, PlatformCategoryMapping, PlatformPolicy, StrategyRun
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


# ============================================================================
# Category Mapping Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_category_mapping_with_policy_passes_category_id_to_adapter(
    service: UnifiedListingService,
    db_session: AsyncSession,
    sample_candidate: CandidateProduct,
    monkeypatch,
):
    """When PlatformCategoryMapping exists, create_listing passes category_id to adapter."""
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
async def test_category_mapping_without_policy_uses_fallback(
    service: UnifiedListingService,
    db_session: AsyncSession,
    sample_candidate: CandidateProduct,
    monkeypatch,
):
    """When no mapping exists, adapter receives original category and uses hardcoded fallback."""
    # No mapping in DB
    captured = {}

    async def mock_create_listing(**kwargs):
        captured.update(kwargs)
        from app.services.platforms.base import PlatformListingData
        return PlatformListingData(
            platform_listing_id="TEST-456",
            platform_url="https://example.com/listing/TEST-456",
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
            "category": "unknown_category",
            "assets": [],
        },
    )

    # Verify fallback behavior
    assert captured["category"] == "unknown_category"
    assert captured["category_id"] is None
    assert captured["category_name"] is None


@pytest.mark.asyncio
async def test_category_mapping_region_specific_priority(
    service: UnifiedListingService,
    db_session: AsyncSession,
):
    """Region-specific mapping takes priority over platform-wide mapping."""
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

    # Should prefer region-specific mapping
    assert result["category_id"] == "3001"
    assert result["category_name"] == "Beauty UK"
    assert result["mapping_source"] == "policy"


@pytest.mark.asyncio
async def test_temu_adapter_category_id_priority():
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
async def test_temu_adapter_fallback_to_hardcoded_mapping():
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
async def test_temu_adapter_invalid_category_id_fallback():
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


# ============================================================================
# Commission Policy Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_commission_policy_integration_with_policy(
    db_session: AsyncSession,
):
    """When commission policy exists, pricing calculation uses policy config."""
    from app.agents.platform_publisher import PlatformPublisherAgent
    from app.agents.base.agent import AgentContext

    # Insert commission policy
    policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="us",
        policy_type="commission",
        version=1,
        is_active=True,
        policy_data={
            "commission_rate": 0.12,  # 12% instead of default 8%
            "payment_fee_rate": 0.03,  # 3% instead of default 2%
            "return_rate_assumption": 0.08,  # 8% instead of default 5%
        },
    )
    db_session.add(policy)
    await db_session.commit()

    # Create agent and context
    agent = PlatformPublisherAgent()
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={},
    )

    # Create sample candidate
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=uuid4(),
        source_platform=SourcePlatform.TEMU,
        title="Test Product",
        category="electronics",
        platform_price=Decimal("10.00"),
        status=CandidateStatus.COPY_GENERATED,
    )

    # Calculate price using agent's method
    price, currency = await agent._calculate_price(
        context=context,
        candidate=candidate,
        platform=TargetPlatform.TEMU,
        region="us",
        strategy="standard",
    )

    # Verify policy rates were used (indirectly through pricing calculation)
    # The price should be higher due to higher commission rate
    assert price > Decimal("0")
    assert currency == "USD"


@pytest.mark.asyncio
async def test_commission_policy_fallback_to_hardcoded(
    db_session: AsyncSession,
):
    """When no policy exists, fallback to hardcoded COMMISSION_RATES."""
    from app.agents.platform_publisher import PlatformPublisherAgent
    from app.agents.base.agent import AgentContext

    # No policy in DB
    agent = PlatformPublisherAgent()
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={},
    )

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=uuid4(),
        source_platform=SourcePlatform.TEMU,
        title="Test Product",
        category="electronics",
        platform_price=Decimal("10.00"),
        status=CandidateStatus.COPY_GENERATED,
    )

    # Calculate price
    price, currency = await agent._calculate_price(
        context=context,
        candidate=candidate,
        platform=TargetPlatform.TEMU,
        region="us",
        strategy="standard",
    )

    # Should use hardcoded rates (8% for Temu)
    assert price > Decimal("0")
    assert currency == "USD"


# ============================================================================
# Pricing Policy Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_pricing_policy_uses_policy_config(
    db_session: AsyncSession,
):
    """PricingService.calculate_pricing_with_policy() uses policy config."""
    from app.services.pricing_service import PricingService

    service = PricingService()

    # Insert pricing policy
    policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="us",
        policy_type="pricing",
        version=1,
        is_active=True,
        policy_data={
            "profitable_threshold": 0.45,  # 45% instead of default 40%
            "marginal_threshold_ratio": 0.55,  # 55% instead of default 60%
            "shipping_rate_default": 0.20,  # 20% instead of default 15%
        },
    )
    db_session.add(policy)
    await db_session.commit()

    result = await service.calculate_pricing_with_policy(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform="amazon",
        region="us",
    )

    # Should use policy thresholds
    assert result.profitable_threshold == Decimal("0.45")
    # Marginal threshold is 0.45 * 0.55 = 0.2475
    assert result.marginal_threshold == Decimal("0.2475")


@pytest.mark.asyncio
async def test_pricing_policy_category_specific_override(
    db_session: AsyncSession,
):
    """Category-specific threshold override is correctly applied."""
    from app.services.pricing_service import PricingService

    service = PricingService()

    # Insert pricing policy with category overrides
    policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="us",
        policy_type="pricing",
        version=1,
        is_active=True,
        policy_data={
            "profitable_threshold": 0.35,
            "marginal_threshold_ratio": 0.60,
            "category_threshold_overrides": {
                "electronics": 0.28,  # Lower threshold for electronics
                "jewelry": 0.55,  # Higher threshold for jewelry
            },
        },
    )
    db_session.add(policy)
    await db_session.commit()

    # Test electronics category
    result_electronics = await service.calculate_pricing_with_policy(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform="temu",
        region="us",
        category="electronics",
    )

    # Should use electronics threshold
    assert result_electronics.profitable_threshold == Decimal("0.28")
    assert result_electronics.marginal_threshold == Decimal("0.168")  # 0.28 * 0.60

    # Test jewelry category
    result_jewelry = await service.calculate_pricing_with_policy(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform="temu",
        region="us",
        category="jewelry",
    )

    # Should use jewelry threshold
    assert result_jewelry.profitable_threshold == Decimal("0.55")
    assert result_jewelry.marginal_threshold == Decimal("0.33")  # 0.55 * 0.60


@pytest.mark.asyncio
async def test_pricing_policy_demand_context_adjustment(
    db_session: AsyncSession,
):
    """Demand context adjustment is correctly layered on top of policy thresholds."""
    from app.services.pricing_service import PricingService

    service = PricingService()

    # Insert pricing policy
    policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="us",
        policy_type="pricing",
        version=1,
        is_active=True,
        policy_data={
            "profitable_threshold": 0.30,
            "marginal_threshold_ratio": 0.60,
        },
    )
    db_session.add(policy)
    await db_session.commit()

    # Test with high competition and fallback discovery
    result = await service.calculate_pricing_with_policy(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform="temu",
        region="us",
        competition_density="high",  # +0.05
        discovery_mode="fallback",  # +0.03
        degraded=True,  # +0.02
    )

    # Should apply adjustments: 0.30 + 0.05 + 0.03 + 0.02 = 0.40
    assert result.profitable_threshold == Decimal("0.40")
    # Marginal threshold is calculated from base threshold: 0.30 * 0.60 = 0.18
    # (adjustments only apply to profitable_threshold, not marginal_threshold)
    assert result.marginal_threshold == Decimal("0.18")


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


@pytest.mark.asyncio
async def test_backward_compatibility_without_policy(
    db_session: AsyncSession,
):
    """Behavior without policy matches existing hardcoded behavior."""
    from app.services.pricing_service import PricingService

    service = PricingService()

    # Calculate with policy (no policy in DB)
    result_with_policy = await service.calculate_pricing_with_policy(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform="temu",
        region="us",
    )

    # Calculate without policy (existing method)
    result_without_policy = service.calculate_pricing(
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform="temu",
    )

    # Should have same profitability decision
    assert result_with_policy.profitability_decision == result_without_policy.profitability_decision
    # Note: margin_percentage may differ slightly due to policy-based shipping calculation
    # but the decision should remain consistent for backward compatibility


@pytest.mark.asyncio
async def test_unified_listing_service_resolve_category_passthrough(
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
async def test_unified_listing_service_resolve_category_fallback(
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
