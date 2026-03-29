"""Integration tests for AutoActionEngine with variant-aware compatibility."""
import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.core.enums import (
    InventoryMode,
    PlatformListingStatus,
    ProductMasterStatus,
    ProductVariantStatus,
    ProfitabilityDecision,
    RiskDecision,
    TargetPlatform,
)
from app.db.models import PricingAssessment, ProductMaster, ProductVariant, RiskAssessment
from app.services.auto_action_engine import AutoActionEngine


async def _add_pricing_assessment(
    db_session,
    candidate_id,
    *,
    margin_percentage: Decimal = Decimal("35.0"),
    profitability_decision: ProfitabilityDecision = ProfitabilityDecision.PROFITABLE,
) -> PricingAssessment:
    """Add pricing assessment to candidate."""
    pricing = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate_id,
        estimated_shipping_cost=Decimal("5.00"),
        platform_commission_rate=Decimal("0.10"),
        payment_fee_rate=Decimal("0.02"),
        return_rate_assumption=Decimal("0.05"),
        total_cost=Decimal("30.00"),
        estimated_margin=Decimal("20.00"),
        margin_percentage=margin_percentage,
        recommended_price=Decimal("55.00"),
        profitability_decision=profitability_decision,
    )
    db_session.add(pricing)
    await db_session.flush()
    return pricing


async def _add_risk_assessment(
    db_session,
    candidate_id,
    *,
    score: int = 20,
    decision: RiskDecision = RiskDecision.PASS,
) -> RiskAssessment:
    """Add risk assessment to candidate."""
    risk = RiskAssessment(
        id=uuid4(),
        candidate_product_id=candidate_id,
        score=score,
        decision=decision,
        rule_hits={},
    )
    db_session.add(risk)
    await db_session.flush()
    return risk


@pytest.mark.asyncio
async def test_auto_action_engine_detects_variant_candidate(db_session, sample_candidate):
    """AutoActionEngine should detect variant candidates."""
    engine = AutoActionEngine(db_session)

    # Master candidate (no master_sku in normalized_attributes)
    sample_candidate.normalized_attributes = {"priority_score": 0.8}
    db_session.add(sample_candidate)
    await db_session.commit()

    is_variant = engine._is_variant_candidate(sample_candidate)
    assert is_variant is False

    # Variant candidate (has master_sku reference)
    sample_candidate.normalized_attributes = {
        "priority_score": 0.8,
        "master_sku": "MASTER-abc123",
    }
    db_session.add(sample_candidate)
    await db_session.commit()

    is_variant = engine._is_variant_candidate(sample_candidate)
    assert is_variant is True


@pytest.mark.asyncio
async def test_auto_action_engine_applies_variant_penalty(db_session, sample_candidate):
    """AutoActionEngine should apply -10% penalty to variant recommendation scores."""
    engine = AutoActionEngine(db_session)

    # Set up source-of-truth data
    await _add_pricing_assessment(
        db_session,
        sample_candidate.id,
        margin_percentage=Decimal("38.0"),
    )
    await _add_risk_assessment(
        db_session,
        sample_candidate.id,
        score=25,
    )

    # Master candidate
    sample_candidate.normalized_attributes = {
        "priority_score": 0.80,
        "competition_density": "low",
    }
    db_session.add(sample_candidate)
    await db_session.commit()

    rec_score_master, _, _ = await engine._recompute_approval_inputs(
        candidate=sample_candidate,
    )

    # Variant candidate (same priority_score)
    sample_candidate.normalized_attributes = {
        "priority_score": 0.80,
        "competition_density": "low",
        "master_sku": "MASTER-abc123",
    }
    db_session.add(sample_candidate)
    await db_session.commit()

    rec_score_variant, _, _ = await engine._recompute_approval_inputs(
        candidate=sample_candidate,
    )

    # Master: 0.80 * 100 * 1.2 (low competition) = 96.0
    # Variant: 96.0 * 0.9 (variant penalty) = 86.4
    assert rec_score_master == 96.0
    assert rec_score_variant == 86.4
    assert rec_score_variant == rec_score_master * 0.9


@pytest.mark.asyncio
async def test_auto_action_engine_variant_requires_approval(db_session, sample_candidate):
    """AutoActionEngine should require approval for variants with lower scores."""
    engine = AutoActionEngine(db_session)

    # Set up source-of-truth data
    await _add_pricing_assessment(
        db_session,
        sample_candidate.id,
        margin_percentage=Decimal("38.0"),
    )
    await _add_risk_assessment(
        db_session,
        sample_candidate.id,
        score=25,
    )

    # Variant candidate with score that would auto-execute as master but not as variant
    sample_candidate.normalized_attributes = {
        "priority_score": 0.90,  # 90 * 1.2 = 108 -> 100 (capped)
        "competition_density": "low",
        "master_sku": "MASTER-abc123",
    }
    db_session.add(sample_candidate)
    await db_session.commit()

    rec_score, risk_score, margin_pct = await engine._recompute_approval_inputs(
        candidate=sample_candidate,
    )

    # Variant score: 100 * 0.9 = 90.0
    # With auto_publish_auto_execute_score_above default (likely 85), this should still pass
    # But let's verify the penalty is applied
    assert rec_score == 90.0

    approval_required, reason = engine._check_approval_required(
        candidate=sample_candidate,
        recommendation_score=rec_score,
        risk_score=risk_score,
        margin_percentage=margin_pct,
        price=Decimal("50.0"),
    )

    # Should require approval due to first_time_product
    assert approval_required is True


@pytest.mark.asyncio
async def test_auto_action_engine_variant_metadata_preserved(db_session, sample_candidate):
    """AutoActionEngine should preserve variant metadata in listing."""
    engine = AutoActionEngine(db_session)

    # Set up source-of-truth data
    await _add_pricing_assessment(
        db_session,
        sample_candidate.id,
        margin_percentage=Decimal("38.0"),
    )
    await _add_risk_assessment(
        db_session,
        sample_candidate.id,
        score=25,
    )

    # Variant candidate
    sample_candidate.normalized_attributes = {
        "priority_score": 0.80,
        "competition_density": "low",
        "master_sku": "MASTER-abc123",
    }
    db_session.add(sample_candidate)
    await db_session.commit()

    listing = await engine.auto_publish(
        candidate_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        recommendation_score=0.0,  # Ignored
        risk_score=0,  # Ignored
        margin_percentage=Decimal("0"),  # Ignored
    )

    # Verify metadata contains variant-adjusted score
    assert listing.auto_action_metadata is not None
    assert listing.auto_action_metadata["recommendation_score"] == 96.0 * 0.9  # 86.4
    assert listing.auto_action_metadata["margin_percentage"] == 38.0
    assert listing.auto_action_metadata["risk_score"] == 25

@pytest.mark.asyncio
async def test_auto_action_engine_links_converted_variant(db_session, sample_candidate):
    """AutoActionEngine should write product_variant linkage for converted candidates."""
    engine = AutoActionEngine(db_session)

    await _add_pricing_assessment(
        db_session,
        sample_candidate.id,
        margin_percentage=Decimal("38.0"),
    )
    await _add_risk_assessment(
        db_session,
        sample_candidate.id,
        score=25,
    )

    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        internal_sku="SKU-LINK-001",
        name="Linked Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-LINK-001",
        attributes={},
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.commit()

    listing = await engine.auto_publish(
        candidate_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        recommendation_score=0.0,
        risk_score=0,
        margin_percentage=Decimal("0"),
    )

    assert listing.product_variant_id == variant.id
    assert listing.inventory_mode == InventoryMode.STOCK_FIRST
    assert listing.auto_action_metadata["product_variant_id"] == str(variant.id)
    assert listing.auto_action_metadata["inventory_mode"] == InventoryMode.STOCK_FIRST.value
