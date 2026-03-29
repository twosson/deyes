"""Phase 1 dual-mode integration tests."""
import pytest
from decimal import Decimal
from uuid import uuid4

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.agents.director_workflow import DirectorWorkflow
from app.core.enums import (
    CandidateStatus,
    PlatformListingStatus,
    ProfitabilityDecision,
    RiskDecision,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import CandidateProduct, PlatformListing, PricingAssessment, ProductMaster, ProductVariant, RiskAssessment, StrategyRun
from app.services.auto_action_engine import AutoActionEngine


class _MockAgent(BaseAgent):
    def __init__(self, name: str, result: AgentResult):
        super().__init__(name)
        self.result = result

    async def execute(self, context: AgentContext) -> AgentResult:
        return self.result


async def _create_strategy_run(db_session) -> StrategyRun:
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


async def _create_candidate(db_session, strategy_run_id) -> CandidateProduct:
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run_id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Dual Mode Product",
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={"priority_score": 0.8, "competition_density": "low"},
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


async def _add_pricing_assessment(db_session, candidate_id) -> PricingAssessment:
    pricing = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate_id,
        estimated_shipping_cost=Decimal("5.00"),
        platform_commission_rate=Decimal("0.10"),
        payment_fee_rate=Decimal("0.02"),
        return_rate_assumption=Decimal("0.05"),
        total_cost=Decimal("30.00"),
        estimated_margin=Decimal("20.00"),
        margin_percentage=Decimal("38.0"),
        recommended_price=Decimal("55.00"),
        profitability_decision=ProfitabilityDecision.PROFITABLE,
    )
    db_session.add(pricing)
    await db_session.flush()
    return pricing


async def _add_risk_assessment(db_session, candidate_id) -> RiskAssessment:
    risk = RiskAssessment(
        id=uuid4(),
        candidate_product_id=candidate_id,
        score=25,
        decision=RiskDecision.PASS,
        rule_hits={},
    )
    db_session.add(risk)
    await db_session.flush()
    return risk


@pytest.mark.asyncio
async def test_phase1_pipeline_converts_then_publishes_with_variant_link(db_session):
    """Eligible candidate should convert to ERP entities and publish with variant linkage."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await _add_pricing_assessment(db_session, candidate.id)
    await _add_risk_assessment(db_session, candidate.id)
    await db_session.commit()

    workflow = DirectorWorkflow()
    workflow.product_selector = _MockAgent(
        "product_selector",
        AgentResult(success=True, output_data={"candidate_ids": [str(candidate.id)]}),
    )
    workflow.pricing_analyst = _MockAgent(
        "pricing_analyst",
        AgentResult(success=True, output_data={"pricing_completed": True}),
    )
    workflow.risk_controller = _MockAgent(
        "risk_controller",
        AgentResult(success=True, output_data={"risk_assessment_completed": True}),
    )
    workflow.copywriter = _MockAgent(
        "copywriter",
        AgentResult(success=True, output_data={"copywriting_completed": True}),
    )

    pipeline_result = await workflow.execute_pipeline(strategy_run.id, db_session)

    assert pipeline_result["status"] == "completed"
    assert pipeline_result["masters_created"] == 1

    master_conversion = pipeline_result["steps"]["master_conversion"][0]
    assert master_conversion["product_master_id"] is not None
    assert master_conversion["product_variant_id"] is not None

    engine = AutoActionEngine(db_session)
    listing = await engine.auto_publish(
        candidate_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        recommendation_score=0.0,
        risk_score=0,
        margin_percentage=Decimal("0"),
    )

    assert listing is not None
    assert listing.candidate_product_id == candidate.id
    assert listing.product_variant_id is not None
    assert listing.inventory_mode is not None
    assert listing.status in {PlatformListingStatus.PENDING_APPROVAL, PlatformListingStatus.APPROVED, PlatformListingStatus.DRAFT}
    assert listing.auto_action_metadata["product_variant_id"] is not None
    assert listing.auto_action_metadata["inventory_mode"] is not None


@pytest.mark.asyncio
async def test_phase1_pipeline_preserves_candidate_only_path_for_ineligible_candidate(db_session):
    """Ineligible candidate should not create ERP entities and old candidate path should remain usable."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)

    pricing = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        estimated_shipping_cost=Decimal("5.00"),
        platform_commission_rate=Decimal("0.10"),
        payment_fee_rate=Decimal("0.02"),
        return_rate_assumption=Decimal("0.05"),
        total_cost=Decimal("30.00"),
        estimated_margin=Decimal("5.00"),
        margin_percentage=Decimal("10.0"),
        recommended_price=Decimal("35.00"),
        profitability_decision=ProfitabilityDecision.UNPROFITABLE,
    )
    db_session.add(pricing)
    await _add_risk_assessment(db_session, candidate.id)
    await db_session.commit()

    workflow = DirectorWorkflow()
    workflow.product_selector = _MockAgent(
        "product_selector",
        AgentResult(success=True, output_data={"candidate_ids": [str(candidate.id)]}),
    )
    workflow.pricing_analyst = _MockAgent(
        "pricing_analyst",
        AgentResult(success=True, output_data={"pricing_completed": True}),
    )
    workflow.risk_controller = _MockAgent(
        "risk_controller",
        AgentResult(success=True, output_data={"risk_assessment_completed": True}),
    )
    workflow.copywriter = _MockAgent(
        "copywriter",
        AgentResult(success=True, output_data={"copywriting_completed": True}),
    )

    pipeline_result = await workflow.execute_pipeline(strategy_run.id, db_session)

    assert pipeline_result["status"] == "completed"
    assert pipeline_result["masters_created"] == 0
    assert pipeline_result["steps"]["master_conversion"] == []

    engine = AutoActionEngine(db_session)
    listing = await engine.auto_publish(
        candidate_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        recommendation_score=0.0,
        risk_score=0,
        margin_percentage=Decimal("0"),
    )

    assert listing.candidate_product_id == candidate.id
    assert listing.product_variant_id is None
    assert listing.inventory_mode is None
