"""Tests for CandidateConversionService."""
import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CandidateStatus,
    ProfitabilityDecision,
    ProductLifecycle,
    RiskDecision,
    SourcePlatform,
    StrategyRunStatus,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    PricingAssessment,
    ProductMaster,
    ProductVariant,
    RiskAssessment,
    StrategyRun,
)
from app.services.candidate_conversion_service import CandidateConversionService


async def _create_strategy_run(db_session: AsyncSession) -> StrategyRun:
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()
    return strategy_run


async def _create_candidate(
    db_session: AsyncSession,
    strategy_run_id,
    *,
    title: str = "Test Product",
) -> CandidateProduct:
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run_id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title=title,
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


async def _add_pricing_assessment(
    db_session: AsyncSession,
    candidate_id,
    *,
    margin_percentage: Decimal = Decimal("35.0"),
    profitability_decision: ProfitabilityDecision = ProfitabilityDecision.PROFITABLE,
) -> PricingAssessment:
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
    db_session: AsyncSession,
    candidate_id,
    *,
    score: int = 20,
    decision: RiskDecision = RiskDecision.PASS,
) -> RiskAssessment:
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
async def test_convert_candidate_to_master_sets_internal_sku(db_session: AsyncSession):
    """Converting candidate to master should create ERP entities and set internal_sku."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = CandidateConversionService()
    result = await service.convert_candidate_to_master(candidate.id, db_session)

    assert result.is_master is True
    assert result.master_candidate_id == candidate.id
    assert len(result.variant_candidate_ids) == 0
    assert result.product_master_id is not None
    assert result.product_variant_id is not None

    await db_session.refresh(candidate)
    assert candidate.internal_sku is not None
    assert candidate.internal_sku.startswith("SKU-")

    master = await db_session.get(ProductMaster, result.product_master_id)
    variant = await db_session.get(ProductVariant, result.product_variant_id)
    assert master is not None
    assert variant is not None
    assert master.candidate_product_id == candidate.id
    assert variant.master_id == master.id
    assert variant.variant_sku == master.internal_sku


@pytest.mark.asyncio
async def test_convert_candidate_to_master_updates_lifecycle(db_session: AsyncSession):
    """Converting candidate to master should update lifecycle_status to APPROVED."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = CandidateConversionService()
    await service.convert_candidate_to_master(candidate.id, db_session)

    await db_session.refresh(candidate)
    assert candidate.lifecycle_status == ProductLifecycle.APPROVED


@pytest.mark.asyncio
async def test_validate_conversion_eligibility_requires_pricing(db_session: AsyncSession):
    """Validation should fail if candidate has no pricing assessment."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = CandidateConversionService()
    eligible, reason = await service.validate_conversion_eligibility(candidate.id, db_session)

    assert eligible is False
    assert reason == "no_pricing_assessment"


@pytest.mark.asyncio
async def test_validate_conversion_eligibility_requires_risk(db_session: AsyncSession):
    """Validation should fail if candidate has no risk assessment."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await _add_pricing_assessment(db_session, candidate.id)
    await db_session.commit()

    service = CandidateConversionService()
    eligible, reason = await service.validate_conversion_eligibility(candidate.id, db_session)

    assert eligible is False
    assert reason == "no_risk_assessment"


@pytest.mark.asyncio
async def test_validate_conversion_eligibility_rejects_unprofitable(db_session: AsyncSession):
    """Validation should fail if candidate is unprofitable."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await _add_pricing_assessment(
        db_session,
        candidate.id,
        margin_percentage=Decimal("10.0"),
        profitability_decision=ProfitabilityDecision.UNPROFITABLE,
    )
    await _add_risk_assessment(db_session, candidate.id)
    await db_session.commit()

    service = CandidateConversionService()
    eligible, reason = await service.validate_conversion_eligibility(candidate.id, db_session)

    assert eligible is False
    assert reason == "unprofitable"


@pytest.mark.asyncio
async def test_validate_conversion_eligibility_rejects_high_risk(db_session: AsyncSession):
    """Validation should fail if candidate is rejected by risk assessment."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await _add_pricing_assessment(db_session, candidate.id)
    await _add_risk_assessment(
        db_session,
        candidate.id,
        score=80,
        decision=RiskDecision.REJECT,
    )
    await db_session.commit()

    service = CandidateConversionService()
    eligible, reason = await service.validate_conversion_eligibility(candidate.id, db_session)

    assert eligible is False
    assert reason == "risk_rejected"


@pytest.mark.asyncio
async def test_validate_conversion_eligibility_accepts_profitable_and_pass(
    db_session: AsyncSession,
):
    """Validation should pass for profitable candidates with PASS risk decision."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await _add_pricing_assessment(
        db_session,
        candidate.id,
        profitability_decision=ProfitabilityDecision.PROFITABLE,
    )
    await _add_risk_assessment(
        db_session,
        candidate.id,
        decision=RiskDecision.PASS,
    )
    await db_session.commit()

    service = CandidateConversionService()
    eligible, reason = await service.validate_conversion_eligibility(candidate.id, db_session)

    assert eligible is True
    assert reason is None


@pytest.mark.asyncio
async def test_validate_conversion_eligibility_accepts_marginal_and_review(
    db_session: AsyncSession,
):
    """Validation should pass for marginal candidates with REVIEW risk decision."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await _add_pricing_assessment(
        db_session,
        candidate.id,
        profitability_decision=ProfitabilityDecision.MARGINAL,
    )
    await _add_risk_assessment(
        db_session,
        candidate.id,
        decision=RiskDecision.REVIEW,
    )
    await db_session.commit()

    service = CandidateConversionService()
    eligible, reason = await service.validate_conversion_eligibility(candidate.id, db_session)

    assert eligible is True
    assert reason is None


@pytest.mark.asyncio
async def test_get_master_candidate_returns_self(db_session: AsyncSession):
    """get_master_candidate should return the linked ProductMaster after conversion."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = CandidateConversionService()
    await service.convert_candidate_to_master(candidate.id, db_session)
    master = await service.get_master_candidate(candidate.id, db_session)

    assert master is not None
    assert master.candidate_product_id == candidate.id


@pytest.mark.asyncio
async def test_get_master_candidate_returns_none_for_missing(db_session: AsyncSession):
    """get_master_candidate should return None for missing candidate."""
    service = CandidateConversionService()
    master = await service.get_master_candidate(uuid4(), db_session)

    assert master is None


@pytest.mark.asyncio
async def test_convert_candidate_auto_links_supplier(db_session: AsyncSession):
    """convert_candidate_to_master should auto-create SupplierOffer from selected SupplierMatch."""
    from app.db.models import SupplierMatch
    from decimal import Decimal

    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    # Create a selected SupplierMatch
    supplier_match = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="Test Supplier",
        supplier_url="https://example.com/supplier",
        supplier_price=Decimal("10.00"),
        moq=100,
        selected=True,
        raw_payload={"alibaba_id": "test123"},
    )
    db_session.add(supplier_match)
    await db_session.commit()

    service = CandidateConversionService()
    result = await service.convert_candidate_to_master(
        candidate.id,
        db_session,
        auto_link_supplier=True,
    )

    assert result.product_variant_id is not None

    # Verify SupplierOffer was created
    from app.db.models import SupplierOffer
    offer_stmt = select(SupplierOffer).where(
        SupplierOffer.variant_id == result.product_variant_id
    )
    offer_result = await db_session.execute(offer_stmt)
    offer = offer_result.scalar_one_or_none()

    assert offer is not None
    assert offer.variant_id == result.product_variant_id
    assert offer.unit_price == Decimal("10.00")
    assert offer.moq == 100


@pytest.mark.asyncio
async def test_convert_candidate_skips_auto_link_if_no_selected_match(db_session: AsyncSession):
    """convert_candidate_to_master should skip auto-link if no selected SupplierMatch."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = CandidateConversionService()
    result = await service.convert_candidate_to_master(
        candidate.id,
        db_session,
        auto_link_supplier=True,
    )

    assert result.product_variant_id is not None

    # Verify no SupplierOffer was created
    from app.db.models import SupplierOffer
    offer_stmt = select(SupplierOffer).where(
        SupplierOffer.variant_id == result.product_variant_id
    )
    offer_result = await db_session.execute(offer_stmt)
    offer = offer_result.scalar_one_or_none()

    assert offer is None


@pytest.mark.asyncio
async def test_convert_candidate_respects_auto_link_flag(db_session: AsyncSession):
    """convert_candidate_to_master should respect auto_link_supplier=False."""
    from app.db.models import SupplierMatch
    from decimal import Decimal

    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    # Create a selected SupplierMatch
    supplier_match = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="Test Supplier",
        supplier_url="https://example.com/supplier",
        supplier_price=Decimal("10.00"),
        moq=100,
        selected=True,
        raw_payload={"alibaba_id": "test123"},
    )
    db_session.add(supplier_match)
    await db_session.commit()

    service = CandidateConversionService()
    result = await service.convert_candidate_to_master(
        candidate.id,
        db_session,
        auto_link_supplier=False,
    )

    assert result.product_variant_id is not None

    # Verify no SupplierOffer was created
    from app.db.models import SupplierOffer
    offer_stmt = select(SupplierOffer).where(
        SupplierOffer.variant_id == result.product_variant_id
    )
    offer_result = await db_session.execute(offer_stmt)
    offer = offer_result.scalar_one_or_none()

    assert offer is None
