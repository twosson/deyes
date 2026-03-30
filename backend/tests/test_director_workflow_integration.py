"""Integration tests for DirectorWorkflow with candidate conversion."""
import pytest
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.agents.content_asset_manager import ContentAssetManagerAgent
from app.agents.director_workflow import DirectorWorkflow
from app.core.enums import (
    CandidateStatus,
    PlatformListingStatus,
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


class _MockAgent(BaseAgent):
    """Mock agent for testing."""

    def __init__(self, name: str, result: AgentResult):
        super().__init__(name)
        self.result = result

    async def execute(self, context: AgentContext) -> AgentResult:
        return self.result


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
async def test_director_workflow_converts_eligible_candidates(db_session: AsyncSession):
    """DirectorWorkflow should convert eligible candidates to masters and generate base assets."""
    from unittest.mock import AsyncMock

    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await _add_pricing_assessment(db_session, candidate.id)
    await _add_risk_assessment(db_session, candidate.id)
    await db_session.commit()

    # Mock clients for content asset manager
    mock_comfyui = AsyncMock()
    mock_comfyui.generate_product_image = AsyncMock(return_value=b"fake_image_data")

    mock_minio = AsyncMock()
    mock_minio.upload_image = AsyncMock(return_value="https://example.com/base.jpg")

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
    workflow.content_asset_manager = ContentAssetManagerAgent(
        comfyui_client=mock_comfyui,
        minio_client=mock_minio,
    )

    result = await workflow.execute_pipeline(strategy_run_id=strategy_run.id, db=db_session)

    assert result["status"] == "completed"
    assert result["candidates_count"] == 1
    assert result["masters_created"] == 1
    assert "master_conversion" in result["steps"]

    # Verify candidate was converted and lifecycle progressed to READY_TO_PUBLISH
    await db_session.refresh(candidate)
    assert candidate.internal_sku is not None
    assert candidate.lifecycle_status == ProductLifecycle.READY_TO_PUBLISH

    # Verify ProductMaster and ProductVariant were created
    master_stmt = select(ProductMaster).where(ProductMaster.candidate_product_id == candidate.id)
    master_result = await db_session.execute(master_stmt)
    master = master_result.scalar_one_or_none()
    assert master is not None
    assert master.internal_sku == candidate.internal_sku

    variant_stmt = select(ProductVariant).where(ProductVariant.master_id == master.id)
    variant_result = await db_session.execute(variant_stmt)
    variant = variant_result.scalars().first()
    assert variant is not None
    assert variant.variant_sku == master.internal_sku


@pytest.mark.asyncio
async def test_director_workflow_skips_ineligible_candidates(db_session: AsyncSession):
    """DirectorWorkflow should skip candidates that fail eligibility checks."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    # Add unprofitable pricing
    await _add_pricing_assessment(
        db_session,
        candidate.id,
        margin_percentage=Decimal("10.0"),
        profitability_decision=ProfitabilityDecision.UNPROFITABLE,
    )
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

    result = await workflow.execute_pipeline(strategy_run_id=strategy_run.id, db=db_session)

    assert result["status"] == "completed"
    assert result["candidates_count"] == 1
    assert result["masters_created"] == 0

    master_stmt = select(ProductMaster).where(ProductMaster.candidate_product_id == candidate.id)
    master_result = await db_session.execute(master_stmt)
    assert master_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_director_workflow_handles_mixed_eligibility(db_session: AsyncSession):
    """DirectorWorkflow should convert eligible and skip ineligible candidates."""
    strategy_run = await _create_strategy_run(db_session)

    # Eligible candidate
    eligible = await _create_candidate(db_session, strategy_run.id, title="Eligible Product")
    await _add_pricing_assessment(db_session, eligible.id)
    await _add_risk_assessment(db_session, eligible.id)

    # Ineligible candidate (rejected risk)
    ineligible = await _create_candidate(db_session, strategy_run.id, title="Rejected Product")
    await _add_pricing_assessment(db_session, ineligible.id)
    await _add_risk_assessment(
        db_session,
        ineligible.id,
        score=80,
        decision=RiskDecision.REJECT,
    )

    await db_session.commit()

    workflow = DirectorWorkflow()
    workflow.product_selector = _MockAgent(
        "product_selector",
        AgentResult(
            success=True,
            output_data={"candidate_ids": [str(eligible.id), str(ineligible.id)]},
        ),
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

    result = await workflow.execute_pipeline(strategy_run_id=strategy_run.id, db=db_session)

    assert result["status"] == "completed"
    assert result["candidates_count"] == 2
    assert result["masters_created"] == 1

    eligible_master_stmt = select(ProductMaster).where(ProductMaster.candidate_product_id == eligible.id)
    eligible_master_result = await db_session.execute(eligible_master_stmt)
    assert eligible_master_result.scalar_one_or_none() is not None

    ineligible_master_stmt = select(ProductMaster).where(ProductMaster.candidate_product_id == ineligible.id)
    ineligible_master_result = await db_session.execute(ineligible_master_stmt)
    assert ineligible_master_result.scalar_one_or_none() is None
