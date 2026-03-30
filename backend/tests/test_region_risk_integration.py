"""Integration tests for region risk rules in regionalized pricing."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TargetPlatform
from app.db.models import PlatformPolicy, RegionRiskRule
from app.services.platform_policy_service import PlatformPolicyService
from app.services.pricing_service import PricingService


@pytest.fixture
def pricing_service() -> PricingService:
    """Create PricingService instance."""
    return PricingService()


@pytest.fixture
def policy_service() -> PlatformPolicyService:
    """Create PlatformPolicyService instance."""
    return PlatformPolicyService()


@pytest.mark.asyncio
async def test_get_risk_rules_prefers_platform_specific_over_global(
    db_session: AsyncSession,
    policy_service: PlatformPolicyService,
):
    """Platform-specific region risk rules should be ordered before global rules."""
    global_rule = RegionRiskRule(
        id=uuid4(),
        platform=None,
        region="de",
        rule_code="battery_compliance",
        severity="medium",
        rule_data={"required_docs": ["msds"]},
        version=1,
        is_active=True,
        notes="Global battery compliance guidance",
    )
    platform_rule = RegionRiskRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        rule_code="battery_compliance",
        severity="high",
        rule_data={"required_docs": ["msds", "ce"]},
        version=1,
        is_active=True,
        notes="Amazon DE requires CE evidence for battery goods",
    )
    db_session.add_all([global_rule, platform_rule])
    await db_session.commit()

    rules = await policy_service.get_risk_rules(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="de",
        rule_code="battery_compliance",
    )

    assert len(rules) == 2
    assert rules[0].platform == TargetPlatform.AMAZON
    assert rules[0].rule_code == "battery_compliance"
    assert rules[0].severity == "high"
    assert rules[0].rule_data == {"required_docs": ["msds", "ce"]}
    assert rules[1].platform is None


@pytest.mark.asyncio
async def test_calculate_regionalized_pricing_outputs_complete_risk_notes(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """Regionalized pricing should include complete serialized risk note data."""
    risk_rule = RegionRiskRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        rule_code="product_compliance",
        severity="high",
        rule_data={
            "required_certifications": ["CE", "RoHS"],
            "review_window_days": 14,
        },
        version=1,
        is_active=True,
        notes="Products sold in Germany require compliance review before listing",
    )
    db_session.add(risk_rule)
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("15.00"),
        platform_price=Decimal("40.00"),
        platform=TargetPlatform.AMAZON,
        region="de",
    )

    assert result["risk_notes"] == [
        {
            "rule_code": "product_compliance",
            "severity": "high",
            "rule_data": {
                "required_certifications": ["CE", "RoHS"],
                "review_window_days": 14,
            },
            "notes": "Products sold in Germany require compliance review before listing",
        }
    ]
    assert result["tax_estimate"] == 0.0
    assert result["margin_check"]["passed"] is True


@pytest.mark.asyncio
async def test_calculate_regionalized_pricing_includes_platform_specific_rule_first(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """Regionalized pricing should return platform-specific risk rules before global rules."""
    global_rule = RegionRiskRule(
        id=uuid4(),
        platform=None,
        region="uk",
        rule_code="packaging_warning",
        severity="low",
        rule_data={"label": "general_uk_packaging"},
        version=1,
        is_active=True,
        notes="General UK packaging guidance",
    )
    platform_rule = RegionRiskRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        rule_code="packaging_warning",
        severity="high",
        rule_data={"label": "temu_uk_packaging", "requires_recycling_mark": True},
        version=1,
        is_active=True,
        notes="Temu UK requires recycling mark validation",
    )
    db_session.add_all([global_rule, platform_rule])
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform=TargetPlatform.TEMU,
        region="uk",
    )

    assert len(result["risk_notes"]) == 2
    assert result["risk_notes"][0]["rule_code"] == "packaging_warning"
    assert result["risk_notes"][0]["severity"] == "high"
    assert result["risk_notes"][0]["rule_data"] == {
        "label": "temu_uk_packaging",
        "requires_recycling_mark": True,
    }
    assert result["risk_notes"][0]["notes"] == "Temu UK requires recycling mark validation"
    assert result["risk_notes"][1]["severity"] == "low"
    assert result["risk_notes"][1]["rule_data"] == {"label": "general_uk_packaging"}


@pytest.mark.asyncio
async def test_calculate_regionalized_pricing_applies_min_margin_policy_threshold(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """Regionalized pricing should enforce min_margin_percentage from pricing policy."""
    policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        policy_type="pricing",
        version=1,
        is_active=True,
        policy_data={
            "profitable_threshold": 0.30,
            "marginal_threshold_ratio": 0.60,
            "shipping_rate_default": 0.15,
            "min_margin_percentage": 0.25,
        },
    )
    db_session.add(policy)
    await db_session.commit()

    passing_result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform=TargetPlatform.TEMU,
        region="uk",
    )
    failing_result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("20.00"),
        platform_price=Decimal("30.00"),
        platform=TargetPlatform.TEMU,
        region="uk",
    )

    assert passing_result["margin_check"]["min_margin_percentage"] == 0.25
    assert passing_result["margin_check"]["actual_margin_percentage"] > 25.0
    assert passing_result["margin_check"]["passed"] is True
    assert passing_result["margin_check"]["note"] is None

    assert failing_result["margin_check"]["min_margin_percentage"] == 0.25
    assert failing_result["margin_check"]["actual_margin_percentage"] < 25.0
    assert failing_result["margin_check"]["passed"] is False
    assert failing_result["margin_check"]["note"] == (
        "Margin 10.00% is below minimum required 25.00% for temu/uk"
    )
