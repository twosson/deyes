"""Tests for ProductMasterService."""
import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CandidateStatus,
    InventoryMode,
    ProductLifecycle,
    ProductMasterStatus,
    ProductVariantStatus,
    ProfitabilityDecision,
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
from app.services.product_master_service import ProductMasterService


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


@pytest.mark.asyncio
async def test_create_from_candidate_creates_master_and_variant(db_session: AsyncSession):
    """create_from_candidate should create ProductMaster and ProductVariant."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = ProductMasterService()
    result = await service.create_from_candidate(candidate.id, db_session)

    assert result.is_new is True
    assert result.product_master is not None
    assert result.product_variant is not None
    assert result.product_master.candidate_product_id == candidate.id
    assert result.product_variant.master_id == result.product_master.id
    assert result.product_master.internal_sku.startswith("SKU-")
    assert result.product_variant.variant_sku == result.product_master.internal_sku


@pytest.mark.asyncio
async def test_create_from_candidate_is_idempotent(db_session: AsyncSession):
    """create_from_candidate should be idempotent."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = ProductMasterService()
    result1 = await service.create_from_candidate(candidate.id, db_session)
    result2 = await service.create_from_candidate(candidate.id, db_session)

    assert result1.product_master.id == result2.product_master.id
    assert result1.product_variant.id == result2.product_variant.id
    assert result1.is_new is True
    assert result2.is_new is False


@pytest.mark.asyncio
async def test_create_from_candidate_updates_candidate_fields(db_session: AsyncSession):
    """create_from_candidate should update candidate internal_sku and lifecycle."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = ProductMasterService()
    result = await service.create_from_candidate(candidate.id, db_session)

    await db_session.refresh(candidate)
    assert candidate.internal_sku == result.product_master.internal_sku
    assert candidate.lifecycle_status == ProductLifecycle.APPROVED


@pytest.mark.asyncio
async def test_create_from_candidate_respects_inventory_mode(db_session: AsyncSession):
    """create_from_candidate should respect inventory_mode parameter."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = ProductMasterService()
    result = await service.create_from_candidate(
        candidate.id,
        db_session,
        inventory_mode=InventoryMode.PRE_ORDER,
    )

    assert result.product_variant.inventory_mode == InventoryMode.PRE_ORDER


@pytest.mark.asyncio
async def test_create_from_candidate_creates_missing_variant(db_session: AsyncSession):
    """create_from_candidate should create missing variant if master exists."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=candidate.id,
        internal_sku="SKU-ORPHAN-001",
        name="Orphan Master",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.commit()

    service = ProductMasterService()
    result = await service.create_from_candidate(candidate.id, db_session)

    assert result.product_master.id == master.id
    assert result.product_variant is not None
    assert result.product_variant.master_id == master.id
    assert result.is_new is False


@pytest.mark.asyncio
async def test_get_master_by_candidate(db_session: AsyncSession):
    """get_master_by_candidate should return linked master."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = ProductMasterService()
    result = await service.create_from_candidate(candidate.id, db_session)

    master = await service.get_master_by_candidate(candidate.id, db_session)
    assert master is not None
    assert master.id == result.product_master.id


@pytest.mark.asyncio
async def test_get_variant_by_sku(db_session: AsyncSession):
    """get_variant_by_sku should return variant by SKU code."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = ProductMasterService()
    result = await service.create_from_candidate(candidate.id, db_session)

    variant = await service.get_variant_by_sku(result.product_variant.variant_sku, db_session)
    assert variant is not None
    assert variant.id == result.product_variant.id


@pytest.mark.asyncio
async def test_list_variants_for_master(db_session: AsyncSession):
    """list_variants_for_master should return all variants."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    await db_session.commit()

    service = ProductMasterService()
    result = await service.create_from_candidate(candidate.id, db_session)

    variants = await service.list_variants_for_master(result.product_master.id, db_session)
    assert len(variants) == 1
    assert variants[0].id == result.product_variant.id
