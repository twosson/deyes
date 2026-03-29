"""Integration tests for DirectorWorkflow with content generation."""
import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.content_asset_manager import ContentAssetManagerAgent
from app.core.enums import (
    AssetType,
    CandidateStatus,
    ContentUsageScope,
    ProfitabilityDecision,
    RiskDecision,
    SourcePlatform,
    StrategyRunStatus,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    ContentAsset,
    PricingAssessment,
    ProductMaster,
    ProductVariant,
    RiskAssessment,
    StrategyRun,
)


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
async def test_content_asset_manager_generate_base_assets(db_session: AsyncSession):
    """ContentAssetManagerAgent should generate base assets for variant."""
    from unittest.mock import AsyncMock

    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await _add_pricing_assessment(db_session, candidate.id)
    await _add_risk_assessment(db_session, candidate.id)
    await db_session.commit()

    # Create master and variant
    from app.services.product_master_service import ProductMasterService

    master_service = ProductMasterService()
    result = await master_service.create_from_candidate(candidate.id, db_session)
    await db_session.commit()

    # Mock clients
    mock_comfyui = AsyncMock()
    mock_comfyui.generate_product_image = AsyncMock(return_value=b"fake_image_data")

    mock_minio = AsyncMock()
    mock_minio.upload_image = AsyncMock(
        return_value="https://example.com/base.jpg"
    )

    # Create agent
    agent = ContentAssetManagerAgent(
        comfyui_client=mock_comfyui,
        minio_client=mock_minio,
    )

    # Create context
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={
            "action": "generate_base_assets",
            "variant_id": str(result.product_variant.id),
            "asset_types": ["main_image"],
            "styles": ["minimalist"],
            "generate_count": 1,
        },
    )

    # Execute
    agent_result = await agent.execute(context)

    # Assertions
    assert agent_result.success is True
    assert agent_result.output_data["assets_created"] == 1
    assert agent_result.output_data["usage_scope"] == "base"

    # Verify asset in database
    await db_session.commit()
    from sqlalchemy import select

    stmt = select(ContentAsset).where(
        ContentAsset.product_variant_id == result.product_variant.id
    )
    assets_result = await db_session.execute(stmt)
    assets = list(assets_result.scalars().all())

    assert len(assets) == 1
    assert assets[0].usage_scope == ContentUsageScope.BASE
    assert assets[0].asset_type == AssetType.MAIN_IMAGE
    assert assets[0].product_variant_id == result.product_variant.id
    assert assets[0].candidate_product_id == candidate.id
