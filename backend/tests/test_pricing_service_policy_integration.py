"""Tests for PricingService policy integration."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProfitabilityDecision, TargetPlatform
from app.db.models import PlatformPolicy
from app.services.pricing_service import PricingService


@pytest.mark.asyncio
async def test_calculate_pricing_with_policy_no_policy_behaves_like_existing(
    db_session: AsyncSession,
):
    """PricingService without policy should behave like existing calculate_pricing."""
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
async def test_calculate_pricing_with_policy_commission_override(
    db_session: AsyncSession,
):
    """PricingService should use commission policy when available."""
    service = PricingService()

    # Insert commission policy
    policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="us",
        policy_type="commission",
        version=1,
        is_active=True,
        policy_data={
            "commission_rate": 0.12,  # 12% instead of default 10%
            "payment_fee_rate": 0.03,  # 3% instead of default 2%
            "return_rate_assumption": 0.08,  # 8% instead of default 5%
        },
    )
    db_session.add(policy)
    await db_session.commit()

    result = await service.calculate_pricing_with_policy(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform="temu",
        region="us",
    )

    # Should use policy rates
    assert result.platform_commission_rate == Decimal("0.12")
    assert result.payment_fee_rate == Decimal("0.03")
    assert result.return_rate_assumption == Decimal("0.08")


@pytest.mark.asyncio
async def test_calculate_pricing_with_policy_pricing_threshold_override(
    db_session: AsyncSession,
):
    """PricingService should use pricing policy thresholds when available."""
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

    # Should use policy thresholds (before demand adjustment)
    # Base threshold is 0.45, no demand adjustment in this test
    assert result.profitable_threshold == Decimal("0.45")
    # Marginal threshold is 0.45 * 0.55 = 0.2475
    assert result.marginal_threshold == Decimal("0.2475")


@pytest.mark.asyncio
async def test_calculate_pricing_with_policy_category_override(
    db_session: AsyncSession,
):
    """PricingService should use category-specific thresholds from policy."""
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
async def test_calculate_pricing_with_policy_demand_context_adjustment(
    db_session: AsyncSession,
):
    """PricingService should apply demand context adjustments on top of policy thresholds."""
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


@pytest.mark.asyncio
async def test_get_effective_pricing_inputs(
    db_session: AsyncSession,
):
    """get_effective_pricing_inputs should return effective pricing inputs from policy."""
    service = PricingService()

    # Insert commission and pricing policies
    commission_policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="us",
        policy_type="commission",
        version=1,
        is_active=True,
        policy_data={
            "commission_rate": 0.18,
            "payment_fee_rate": 0.025,
            "return_rate_assumption": 0.06,
        },
    )
    db_session.add(commission_policy)

    pricing_policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="us",
        policy_type="pricing",
        version=1,
        is_active=True,
        policy_data={
            "profitable_threshold": 0.42,
            "marginal_threshold_ratio": 0.65,
            "shipping_rate_default": 0.18,
        },
    )
    db_session.add(pricing_policy)
    await db_session.commit()

    inputs = await service.get_effective_pricing_inputs(
        db=db_session,
        platform="amazon",
        region="us",
    )

    assert inputs["commission_rate"] == Decimal("0.18")
    assert inputs["payment_fee_rate"] == Decimal("0.025")
    assert inputs["return_rate_assumption"] == Decimal("0.06")
    assert inputs["shipping_rate"] == Decimal("0.18")
    assert inputs["profitable_threshold"] == Decimal("0.42")
    assert inputs["marginal_threshold"] == Decimal("0.273")  # 0.42 * 0.65


@pytest.mark.asyncio
async def test_get_effective_pricing_inputs_with_category_override(
    db_session: AsyncSession,
):
    """get_effective_pricing_inputs should apply category overrides."""
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
                "beauty": 0.48,
            },
        },
    )
    db_session.add(policy)
    await db_session.commit()

    inputs = await service.get_effective_pricing_inputs(
        db=db_session,
        platform="temu",
        region="us",
        category="beauty",
    )

    # Should use beauty category threshold
    assert inputs["profitable_threshold"] == Decimal("0.48")
    assert inputs["marginal_threshold"] == Decimal("0.288")  # 0.48 * 0.60
