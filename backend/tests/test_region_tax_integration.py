"""Integration tests for RegionTaxRule application in regionalized pricing (Stage 5 C3).

Tests cover:
1. Tax estimation: tax_estimate calculation, multiple rule accumulation, priority
2. Tax breakdown: structure, tax_type, tax_rate, tax_amount fields
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TargetPlatform
from app.db.models import RegionTaxRule
from app.services.pricing_service import PricingService


@pytest.fixture
def pricing_service() -> PricingService:
    """Create PricingService instance."""
    return PricingService()


# ============================================================================
# Tax Estimation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_tax_estimate_single_rule(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """calculate_regionalized_pricing() correctly calculates tax_estimate with one rule.

    UK VAT at 20% on a platform price of 30.00 should produce tax_estimate of 6.00.
    """
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

    # tax_estimate = 30.00 * 0.20 = 6.00
    assert result["tax_estimate"] == 6.0


@pytest.mark.asyncio
async def test_tax_estimate_multiple_rules_accumulate(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """Multiple tax rules accumulate correctly in tax_estimate.

    DE region with VAT (19%) + import tax (5%) should sum to 24% of platform price.
    """
    vat_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        tax_type="vat",
        tax_rate=Decimal("0.19"),
        version=1,
        is_active=True,
    )
    import_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        tax_type="import_tax",
        tax_rate=Decimal("0.05"),
        version=1,
        is_active=True,
    )
    db_session.add_all([vat_rule, import_rule])
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("15.00"),
        platform_price=Decimal("50.00"),
        platform=TargetPlatform.AMAZON,
        region="de",
    )

    # tax_estimate = 50.00 * 0.19 + 50.00 * 0.05 = 9.50 + 2.50 = 12.00
    assert result["tax_estimate"] == 12.0
    assert len(result["tax_breakdown"]) == 2


@pytest.mark.asyncio
async def test_tax_rules_order_platform_specific_before_global(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """Platform-specific tax rules are returned before global rules and both are applied.

    The current implementation orders platform-specific rules first in
    PlatformPolicyService.get_tax_rules(), but calculate_regionalized_pricing()
    applies every returned rule when computing the tax estimate.
    """
    global_rule = RegionTaxRule(
        id=uuid4(),
        platform=None,
        region="fr",
        tax_type="vat",
        tax_rate=Decimal("0.15"),
        version=1,
        is_active=True,
    )
    temu_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="fr",
        tax_type="vat",
        tax_rate=Decimal("0.20"),
        version=1,
        is_active=True,
    )
    db_session.add_all([global_rule, temu_rule])
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("100.00"),
        platform=TargetPlatform.TEMU,
        region="fr",
    )

    assert len(result["tax_breakdown"]) == 2
    assert result["tax_breakdown"][0]["tax_rate"] == 0.20
    assert result["tax_breakdown"][1]["tax_rate"] == 0.15
    # Tax estimate = 100.00 * 0.20 + 100.00 * 0.15 = 35.00
    assert result["tax_estimate"] == 35.0


@pytest.mark.asyncio
async def test_tax_estimate_global_rule_only_without_platform_match(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """Global (NULL platform) rules are applied when no platform-specific rule exists."""
    global_rule = RegionTaxRule(
        id=uuid4(),
        platform=None,
        region="au",
        tax_type="gst",
        tax_rate=Decimal("0.10"),
        version=1,
        is_active=True,
    )
    db_session.add(global_rule)
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("20.00"),
        platform_price=Decimal("50.00"),
        platform=TargetPlatform.OZON,  # Ozon, not Temu - global rule should still apply
        region="au",
    )

    # GST = 50.00 * 0.10 = 5.00
    assert result["tax_estimate"] == 5.0
    assert len(result["tax_breakdown"]) == 1
    assert result["tax_breakdown"][0]["tax_type"] == "gst"


@pytest.mark.asyncio
async def test_tax_estimate_no_rules_returns_zero(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """tax_estimate is 0.0 when no tax rules exist for the region."""
    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
        platform=TargetPlatform.TEMU,
        region="us",  # No tax rules for US in this test
    )

    assert result["tax_estimate"] == 0.0
    assert result["tax_breakdown"] == []


# ============================================================================
# Tax Breakdown Tests
# ============================================================================


@pytest.mark.asyncio
async def test_tax_breakdown_structure(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """tax_breakdown includes all applicable tax rules with correct field structure."""
    vat_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        tax_type="vat",
        tax_rate=Decimal("0.20"),
        version=1,
        is_active=True,
        applies_to={"categories": ["electronics", "home"]},
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

    assert len(result["tax_breakdown"]) == 1
    entry = result["tax_breakdown"][0]

    # Required fields
    assert "tax_type" in entry
    assert "tax_rate" in entry
    assert "tax_amount" in entry
    assert "applies_to" in entry

    # Values
    assert entry["tax_type"] == "vat"
    assert entry["tax_rate"] == 0.20
    assert entry["tax_amount"] == 6.0
    assert entry["applies_to"] == {"categories": ["electronics", "home"]}


@pytest.mark.asyncio
async def test_tax_breakdown_multiple_rules_all_present(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """tax_breakdown includes all rules when multiple tax types apply."""
    vat_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        tax_type="vat",
        tax_rate=Decimal("0.19"),
        version=1,
        is_active=True,
    )
    sales_tax_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        tax_type="sales_tax",
        tax_rate=Decimal("0.05"),
        version=1,
        is_active=True,
    )
    eco_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="de",
        tax_type="eco_tax",
        tax_rate=Decimal("0.01"),
        version=1,
        is_active=True,
    )
    db_session.add_all([vat_rule, sales_tax_rule, eco_rule])
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("100.00"),
        platform=TargetPlatform.AMAZON,
        region="de",
    )

    assert len(result["tax_breakdown"]) == 3

    # All tax types present
    tax_types = {entry["tax_type"] for entry in result["tax_breakdown"]}
    assert tax_types == {"vat", "sales_tax", "eco_tax"}

    # All amounts correct: 19 + 5 + 1 = 25%
    total = sum(entry["tax_amount"] for entry in result["tax_breakdown"])
    assert total == 25.0


@pytest.mark.asyncio
async def test_tax_breakdown_types_are_strings_and_floats(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """tax_type is a string and tax_rate/tax_amount are floats (JSON-serializable)."""
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

    entry = result["tax_breakdown"][0]

    # Type assertions for JSON serialization compatibility
    assert isinstance(entry["tax_type"], str)
    assert isinstance(entry["tax_rate"], float)
    assert isinstance(entry["tax_amount"], float)


@pytest.mark.asyncio
async def test_tax_breakdown_rate_precision(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """tax_rate preserves precision from the database (4 decimal places)."""
    precise_rule = RegionTaxRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        tax_type="vat",
        tax_rate=Decimal("0.1950"),
        version=1,
        is_active=True,
    )
    db_session.add(precise_rule)
    await db_session.commit()

    result = await pricing_service.calculate_regionalized_pricing(
        db=db_session,
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("100.00"),
        platform=TargetPlatform.TEMU,
        region="uk",
    )

    entry = result["tax_breakdown"][0]
    assert entry["tax_rate"] == 0.1950
    # tax_amount = 100.00 * 0.1950 = 19.50
    assert entry["tax_amount"] == 19.5


# ============================================================================
# Integration: Full Output Structure Validation
# ============================================================================


@pytest.mark.asyncio
async def test_regionalized_pricing_output_structure_complete_with_tax(
    db_session: AsyncSession,
    pricing_service: PricingService,
):
    """calculate_regionalized_pricing output contains all required fields with tax data."""
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

    # Top-level fields
    assert "local_price" in result
    assert "local_currency" in result
    assert "base_currency_profit" in result
    assert "base_currency" in result

    # Tax fields
    assert "tax_estimate" in result
    assert "tax_breakdown" in result

    # Related fields
    assert "risk_notes" in result
    assert "pricing_result" in result
    assert "currency_metadata" in result
    assert "margin_check" in result

    # Values are correct types
    assert isinstance(result["tax_estimate"], float)
    assert isinstance(result["tax_breakdown"], list)
    assert isinstance(result["risk_notes"], list)
    assert isinstance(result["pricing_result"], dict)
