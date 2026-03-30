"""Tests for regionalized pricing and profit conversion (Stage 5 C3)."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TargetPlatform
from app.db.models import ExchangeRate, PlatformPolicy, RegionRiskRule, RegionTaxRule
from app.services.pricing_service import PricingService
from app.services.profit_ledger_service import ProfitLedgerService
from app.services.platform_policy_service import PlatformPolicyService


@pytest.fixture
def pricing_service() -> PricingService:
    """Create PricingService instance."""
    return PricingService()


@pytest.fixture
def profit_service() -> ProfitLedgerService:
    """Create ProfitLedgerService instance."""
    return ProfitLedgerService()


@pytest.fixture
def policy_service() -> PlatformPolicyService:
    """Create PlatformPolicyService instance."""
    return PlatformPolicyService()


# ============================================================================
# PlatformPolicyService.get_tax_rules tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_tax_rules_returns_empty_when_no_rules(
    db_session: AsyncSession,
    policy_service: PlatformPolicyService,
):
    """get_tax_rules should return empty list when no rules exist."""
    rules = await policy_service.get_tax_rules(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
    )

    assert rules == []


@pytest.mark.asyncio
async def test_get_tax_rules_returns_active_rules(
    db_session: AsyncSession,
    policy_service: PlatformPolicyService,
):
    """get_tax_rules should return active tax rules for platform/region."""
    # Create tax rules
    vat_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        tax_type="vat",
        tax_rate=Decimal("0.20"),
        version=1,
        is_active=True,
    )
    db_session.add(vat_rule)
    await db_session.commit()

    rules = await policy_service.get_tax_rules(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="uk",
    )

    assert len(rules) == 1
    assert rules[0].tax_type == "vat"
    assert rules[0].tax_rate == Decimal("0.20")


@pytest.mark.asyncio
async def test_get_tax_rules_filters_by_tax_type(
    db_session: AsyncSession,
    policy_service: PlatformPolicyService,
):
    """get_tax_rules should filter by tax_type when provided."""
    # Create multiple tax rules
    vat_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        tax_type="vat",
        tax_rate=Decimal("0.20"),
        version=1,
        is_active=True,
    )
    sales_tax_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        tax_type="sales_tax",
        tax_rate=Decimal("0.05"),
        version=1,
        is_active=True,
    )
    db_session.add_all([vat_rule, sales_tax_rule])
    await db_session.commit()

    vat_rules = await policy_service.get_tax_rules(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="uk",
        tax_type="vat",
    )

    assert len(vat_rules) == 1
    assert vat_rules[0].tax_type == "vat"


@pytest.mark.asyncio
async def test_get_tax_rules_prefers_platform_specific_over_global(
    db_session: AsyncSession,
    policy_service: PlatformPolicyService,
):
    """get_tax_rules should prefer platform-specific rules over global rules."""
    # Global rule (no platform)
    global_rule = RegionTaxRule(
        id=uuid4(),
        platform=None,
        region="uk",
        tax_type="vat",
        tax_rate=Decimal("0.15"),
        version=1,
        is_active=True,
    )
    # Platform-specific rule
    platform_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        tax_type="vat",
        tax_rate=Decimal("0.20"),
        version=1,
        is_active=True,
    )
    db_session.add_all([global_rule, platform_rule])
    await db_session.commit()

    rules = await policy_service.get_tax_rules(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="uk",
        tax_type="vat",
    )

    # Platform-specific should come first
    assert len(rules) == 2
    assert rules[0].platform == TargetPlatform.TEMU
    assert rules[0].tax_rate == Decimal("0.20")


# ============================================================================
# PlatformPolicyService.get_risk_rules tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_risk_rules_returns_empty_when_no_rules(
    db_session: AsyncSession,
    policy_service: PlatformPolicyService,
):
    """get_risk_rules should return empty list when no rules exist."""
    rules = await policy_service.get_risk_rules(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
    )

    assert rules == []


@pytest.mark.asyncio
async def test_get_risk_rules_returns_active_rules(
    db_session: AsyncSession,
    policy_service: PlatformPolicyService,
):
    """get_risk_rules should return active risk rules for platform/region."""
    risk_rule = RegionRiskRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        rule_code="product_compliance",
        severity="high",
        rule_data={"required_certifications": ["CE"]},
        version=1,
        is_active=True,
    )
    db_session.add(risk_rule)
    await db_session.commit()

    rules = await policy_service.get_risk_rules(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="de",
    )

    assert len(rules) == 1
    assert rules[0].rule_code == "product_compliance"
    assert rules[0].severity == "high"


@pytest.mark.asyncio
async def test_get_risk_rules_filters_by_rule_code(
    db_session: AsyncSession,
    policy_service: PlatformPolicyService,
):
    """get_risk_rules should filter by rule_code when provided."""
    compliance_rule = RegionRiskRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        rule_code="product_compliance",
        severity="high",
        rule_data={"required_certifications": ["CE"]},
        version=1,
        is_active=True,
    )
    labeling_rule = RegionRiskRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        rule_code="labeling",
        severity="medium",
        rule_data={"required_labels": ["origin"]},
        version=1,
        is_active=True,
    )
    db_session.add_all([compliance_rule, labeling_rule])
    await db_session.commit()

    rules = await policy_service.get_risk_rules(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="de",
        rule_code="labeling",
    )

    assert len(rules) == 1
    assert rules[0].rule_code == "labeling"


# ============================================================================
# PricingService.calculate_regionalized_pricing tests
# ============================================================================


@pytest.mark.asyncio
async def test_calculate_regionalized_pricing_no_rules_fallback(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """calculate_regionalized_pricing should work without tax/risk rules."""
    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform=TargetPlatform.TEMU,
        region="us",
    )

    assert result["local_price"] == 30.0
    assert result["local_currency"] == "USD"
    assert result["base_currency"] == "USD"
    assert result["tax_estimate"] == 0.0
    assert result["tax_breakdown"] == []
    assert result["risk_notes"] == []
    assert "pricing_result" in result
    assert "margin_check" in result


@pytest.mark.asyncio
async def test_calculate_regionalized_pricing_with_tax_rules(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """calculate_regionalized_pricing should calculate tax estimate from rules."""
    # Create tax rules
    vat_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        tax_type="vat",
        tax_rate=Decimal("0.20"),
        version=1,
        is_active=True,
    )
    db_session.add(vat_rule)
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform=TargetPlatform.TEMU,
        region="uk",
    )

    # Tax estimate = 30.00 * 0.20 = 6.00
    assert result["tax_estimate"] == 6.0
    assert len(result["tax_breakdown"]) == 1
    assert result["tax_breakdown"][0]["tax_type"] == "vat"
    assert result["tax_breakdown"][0]["tax_rate"] == 0.20
    assert result["tax_breakdown"][0]["tax_amount"] == 6.0


@pytest.mark.asyncio
async def test_calculate_regionalized_pricing_with_risk_rules(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """calculate_regionalized_pricing should include risk notes from rules."""
    # Create risk rules
    risk_rule = RegionRiskRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        rule_code="product_compliance",
        severity="high",
        rule_data={"required_certifications": ["CE"]},
        version=1,
        is_active=True,
        notes="Products sold in DE require CE certification",
    )
    db_session.add(risk_rule)
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("15.00"),
        platform_price=Decimal("35.00"),
        platform=TargetPlatform.AMAZON,
        region="de",
    )

    assert len(result["risk_notes"]) == 1
    assert result["risk_notes"][0]["rule_code"] == "product_compliance"
    assert result["risk_notes"][0]["severity"] == "high"
    assert "CE" in result["risk_notes"][0]["rule_data"]["required_certifications"]


@pytest.mark.asyncio
async def test_calculate_regionalized_pricing_with_min_margin_check(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """calculate_regionalized_pricing should check minimum margin from policy."""
    # Create pricing policy with min_margin_percentage
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
            "min_margin_percentage": 0.25,  # 25% minimum margin
        },
    )
    db_session.add(policy)
    await db_session.commit()

    # Case 1: Margin above minimum
    result_high_margin = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),  # High margin
        platform=TargetPlatform.TEMU,
        region="uk",
    )

    assert result_high_margin["margin_check"]["passed"] is True
    assert result_high_margin["margin_check"]["note"] is None

    # Case 2: Margin below minimum
    result_low_margin = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("25.00"),
        platform_price=Decimal("30.00"),  # Low margin
        platform=TargetPlatform.TEMU,
        region="uk",
    )

    assert result_low_margin["margin_check"]["passed"] is False
    assert "below minimum required" in result_low_margin["margin_check"]["note"]


@pytest.mark.asyncio
async def test_calculate_regionalized_pricing_currency_conversion(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """calculate_regionalized_pricing should convert profit to base currency."""
    # Create exchange rate
    exchange_rate = ExchangeRate(
        id=uuid4(),
        base_currency="GBP",
        quote_currency="USD",
        rate=Decimal("1.25"),  # 1 GBP = 1.25 USD
        rate_date=date.today(),
        is_active=True,
    )
    db_session.add(exchange_rate)
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),  # in USD
        platform_price=Decimal("20.00"),  # in GBP
        platform=TargetPlatform.TEMU,
        region="uk",
        base_currency="USD",
        local_currency="GBP",
    )

    assert result["local_currency"] == "GBP"
    assert result["base_currency"] == "USD"
    assert result["currency_metadata"]["conversion_applied"] is True
    # Profit ~ 20 - 10 - fees, converted to USD
    assert result["base_currency_profit"] != result["pricing_result"]["estimated_margin"]


# ============================================================================
# ProfitLedgerService.get_profit_snapshot_in_currency tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_profit_snapshot_in_currency_same_currency(
    db_session: AsyncSession,
    profit_service: ProfitLedgerService,
):
    """get_profit_snapshot_in_currency should return copy for same currency."""
    snapshot = await profit_service.get_profit_snapshot_in_currency(
        db=db_session,
        target_currency="USD",
        source_currency="USD",
    )

    assert snapshot["currency"] == "USD"
    assert snapshot["source_currency"] == "USD"
    assert snapshot["conversion_applied"] is False
    assert snapshot["entry_count"] == 0


@pytest.mark.asyncio
async def test_get_profit_snapshot_in_currency_conversion(
    db_session: AsyncSession,
    profit_service: ProfitLedgerService,
):
    """get_profit_snapshot_in_currency should convert monetary fields."""
    # Create exchange rate
    exchange_rate = ExchangeRate(
        id=uuid4(),
        base_currency="EUR",
        quote_currency="USD",
        rate=Decimal("1.10"),  # 1 EUR = 1.10 USD
        rate_date=date.today(),
        is_active=True,
    )
    db_session.add(exchange_rate)
    await db_session.commit()

    snapshot = await profit_service.get_profit_snapshot_in_currency(
        db=db_session,
        target_currency="USD",
        source_currency="EUR",
    )

    assert snapshot["currency"] == "USD"
    assert snapshot["source_currency"] == "EUR"
    assert snapshot["conversion_applied"] is True


# ============================================================================
# ProfitLedgerService.get_regionalized_profit_snapshot tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_regionalized_profit_snapshot_no_rules(
    db_session: AsyncSession,
    profit_service: ProfitLedgerService,
):
    """get_regionalized_profit_snapshot should work without tax/risk rules."""
    result = await profit_service.get_regionalized_profit_snapshot(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
    )

    assert result["platform"] == "temu"
    assert result["region"] == "us"
    assert result["entry_count"] == 0
    assert result["tax_estimate"] == 0.0
    assert result["tax_rule_count"] == 0
    assert result["risk_notes"] == []
    assert "base_currency_snapshot" in result


@pytest.mark.asyncio
async def test_get_regionalized_profit_snapshot_with_tax_rules(
    db_session: AsyncSession,
    profit_service: ProfitLedgerService,
):
    """get_regionalized_profit_snapshot should calculate tax from rules."""
    # Create tax rules
    vat_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        tax_type="vat",
        tax_rate=Decimal("0.19"),
        version=1,
        is_active=True,
    )
    db_session.add(vat_rule)
    await db_session.commit()

    result = await profit_service.get_regionalized_profit_snapshot(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="de",
    )

    assert result["tax_rule_count"] == 1
    # Tax estimate = 0 * 0.19 = 0 (no revenue)
    assert result["tax_estimate"] == 0.0


@pytest.mark.asyncio
async def test_get_regionalized_profit_snapshot_with_risk_rules(
    db_session: AsyncSession,
    profit_service: ProfitLedgerService,
):
    """get_regionalized_profit_snapshot should include risk notes."""
    # Create risk rules
    risk_rule = RegionRiskRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="uk",
        rule_code="brexit_compliance",
        severity="medium",
        rule_data={"required_docs": ["EORI"]},
        version=1,
        is_active=True,
    )
    db_session.add(risk_rule)
    await db_session.commit()

    result = await profit_service.get_regionalized_profit_snapshot(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="uk",
    )

    assert len(result["risk_notes"]) == 1
    assert result["risk_notes"][0]["rule_code"] == "brexit_compliance"
    assert result["risk_notes"][0]["severity"] == "medium"
