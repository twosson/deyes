"""Tests for lifecycle engine service."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SkuLifecycleState
from app.db.models import (
    LifecycleRule,
    LifecycleTransitionLog,
    ProductMaster,
    ProductVariant,
    SkuLifecycleStateModel,
)
from app.services.lifecycle_engine_service import LifecycleEngineService


@pytest.mark.asyncio
async def test_get_current_state_returns_discovering_for_new_variant(db_session: AsyncSession):
    """LifecycleEngineService should return DISCOVERING for new variant without state record."""
    service = LifecycleEngineService()

    # Create a product variant without lifecycle state
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MASTER-001",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-001",
    )
    db_session.add(variant)
    await db_session.commit()

    state = await service.get_current_state(db_session, variant.id)

    assert state == SkuLifecycleState.DISCOVERING


@pytest.mark.asyncio
async def test_get_current_state_returns_existing_state(db_session: AsyncSession):
    """LifecycleEngineService should return existing state from database."""
    service = LifecycleEngineService()

    # Create variant with lifecycle state
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MASTER-002",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-002",
    )
    db_session.add(variant)

    state_record = SkuLifecycleStateModel(
        id=uuid4(),
        product_variant_id=variant.id,
        current_state=SkuLifecycleState.TESTING,
        entered_at=datetime.now(timezone.utc),
    )
    db_session.add(state_record)
    await db_session.commit()

    state = await service.get_current_state(db_session, variant.id)

    assert state == SkuLifecycleState.TESTING


@pytest.mark.asyncio
async def test_apply_transition_creates_new_state_record(db_session: AsyncSession):
    """LifecycleEngineService should create state record when transitioning from default state."""
    service = LifecycleEngineService()

    # Create variant without state
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MASTER-003",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-003",
    )
    db_session.add(variant)
    await db_session.commit()

    result = await service.apply_transition(
        db=db_session,
        product_variant_id=variant.id,
        target_state=SkuLifecycleState.TESTING,
        reason="First listing created",
        trigger_source="manual",
    )

    assert result is True

    # Verify state record created
    state = await service.get_current_state(db_session, variant.id)
    assert state == SkuLifecycleState.TESTING


@pytest.mark.asyncio
async def test_apply_transition_updates_existing_state(db_session: AsyncSession):
    """LifecycleEngineService should update existing state record."""
    service = LifecycleEngineService()

    # Create variant with existing state
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MASTER-004",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-004",
    )
    db_session.add(variant)

    state_record = SkuLifecycleStateModel(
        id=uuid4(),
        product_variant_id=variant.id,
        current_state=SkuLifecycleState.TESTING,
        entered_at=datetime.now(timezone.utc),
    )
    db_session.add(state_record)
    await db_session.commit()

    result = await service.apply_transition(
        db=db_session,
        product_variant_id=variant.id,
        target_state=SkuLifecycleState.SCALING,
        reason="Revenue threshold met",
        trigger_source="lifecycle_engine",
    )

    assert result is True

    # Verify state updated
    state = await service.get_current_state(db_session, variant.id)
    assert state == SkuLifecycleState.SCALING


@pytest.mark.asyncio
async def test_apply_transition_returns_false_for_same_state(db_session: AsyncSession):
    """LifecycleEngineService should return False when target state equals current state."""
    service = LifecycleEngineService()

    # Create variant with state
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MASTER-005",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-005",
    )
    db_session.add(variant)

    state_record = SkuLifecycleStateModel(
        id=uuid4(),
        product_variant_id=variant.id,
        current_state=SkuLifecycleState.STABLE,
        entered_at=datetime.now(timezone.utc),
    )
    db_session.add(state_record)
    await db_session.commit()

    result = await service.apply_transition(
        db=db_session,
        product_variant_id=variant.id,
        target_state=SkuLifecycleState.STABLE,
        reason="No change",
        trigger_source="manual",
    )

    assert result is False


@pytest.mark.asyncio
async def test_apply_transition_creates_transition_log(db_session: AsyncSession):
    """LifecycleEngineService should create transition log entry."""
    service = LifecycleEngineService()

    # Create variant with state
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MASTER-006",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-006",
    )
    db_session.add(variant)

    state_record = SkuLifecycleStateModel(
        id=uuid4(),
        product_variant_id=variant.id,
        current_state=SkuLifecycleState.SCALING,
        entered_at=datetime.now(timezone.utc),
    )
    db_session.add(state_record)
    await db_session.commit()

    await service.apply_transition(
        db=db_session,
        product_variant_id=variant.id,
        target_state=SkuLifecycleState.STABLE,
        reason="14 days in scaling",
        trigger_source="lifecycle_engine",
        trigger_payload={"days_in_scaling": 14},
    )

    # Verify transition log created
    from sqlalchemy import select
    stmt = select(LifecycleTransitionLog).where(
        LifecycleTransitionLog.product_variant_id == variant.id
    )
    result = await db_session.execute(stmt)
    logs = list(result.scalars().all())

    assert len(logs) == 1
    assert logs[0].from_state == SkuLifecycleState.SCALING
    assert logs[0].to_state == SkuLifecycleState.STABLE
    assert logs[0].triggered_by == "lifecycle_engine"
    assert logs[0].trigger_data == {"days_in_scaling": 14}


@pytest.mark.asyncio
async def test_apply_transition_stores_reason_in_metadata(db_session: AsyncSession):
    """LifecycleEngineService should store transition reason in state metadata."""
    service = LifecycleEngineService()

    # Create variant
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MASTER-007",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-007",
    )
    db_session.add(variant)
    await db_session.commit()

    await service.apply_transition(
        db=db_session,
        product_variant_id=variant.id,
        target_state=SkuLifecycleState.DECLINING,
        reason="Revenue drop > 30%",
        trigger_source="lifecycle_engine",
    )

    # Verify reason stored in metadata
    from sqlalchemy import select
    stmt = select(SkuLifecycleStateModel).where(
        SkuLifecycleStateModel.product_variant_id == variant.id
    )
    result = await db_session.execute(stmt)
    state_record = result.scalar_one()

    assert state_record.state_metadata is not None
    assert state_record.state_metadata["reason"] == "Revenue drop > 30%"


@pytest.mark.asyncio
async def test_load_rules_returns_active_rules_only(db_session: AsyncSession):
    """LifecycleEngineService should load only active rules."""
    service = LifecycleEngineService()

    # Create active and inactive rules
    active_rule = LifecycleRule(
        id=uuid4(),
        from_state=SkuLifecycleState.TESTING,
        to_state=SkuLifecycleState.SCALING,
        rule_name="testing_to_scaling",
        conditions={"revenue_7d": 1000, "margin_7d": 0.20},
        priority=10,
        is_active=True,
    )
    db_session.add(active_rule)

    inactive_rule = LifecycleRule(
        id=uuid4(),
        from_state=SkuLifecycleState.SCALING,
        to_state=SkuLifecycleState.STABLE,
        rule_name="scaling_to_stable",
        conditions={"days_in_scaling": 14},
        priority=5,
        is_active=False,
    )
    db_session.add(inactive_rule)
    await db_session.commit()

    rules = await service.load_rules(db_session)

    assert len(rules) == 1
    assert rules[0].rule_name == "testing_to_scaling"
    assert rules[0].is_active is True


@pytest.mark.asyncio
async def test_evaluate_state_returns_current_state_and_metadata(db_session: AsyncSession):
    """LifecycleEngineService should evaluate state and return metadata."""
    service = LifecycleEngineService()

    # Create variant with state
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MASTER-008",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-008",
    )
    db_session.add(variant)

    state_record = SkuLifecycleStateModel(
        id=uuid4(),
        product_variant_id=variant.id,
        current_state=SkuLifecycleState.STABLE,
        entered_at=datetime.now(timezone.utc),
    )
    db_session.add(state_record)
    await db_session.commit()

    result = await service.evaluate_state(db_session, variant.id)

    assert result["current_state"] == SkuLifecycleState.STABLE
    assert "confidence_score" in result
    assert "reasons" in result
    assert "should_transition" in result
    assert "suggested_next_state" in result


@pytest.mark.asyncio
async def test_apply_transition_handles_multiple_transitions(db_session: AsyncSession):
    """LifecycleEngineService should handle multiple transitions correctly."""
    service = LifecycleEngineService()

    # Create variant
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-MASTER-009",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-SKU-009",
    )
    db_session.add(variant)
    await db_session.commit()

    # Apply multiple transitions
    await service.apply_transition(
        db=db_session,
        product_variant_id=variant.id,
        target_state=SkuLifecycleState.TESTING,
        reason="First listing",
        trigger_source="manual",
    )

    await service.apply_transition(
        db=db_session,
        product_variant_id=variant.id,
        target_state=SkuLifecycleState.SCALING,
        reason="Revenue threshold",
        trigger_source="lifecycle_engine",
    )

    await service.apply_transition(
        db=db_session,
        product_variant_id=variant.id,
        target_state=SkuLifecycleState.STABLE,
        reason="14 days stable",
        trigger_source="lifecycle_engine",
    )

    # Verify final state
    state = await service.get_current_state(db_session, variant.id)
    assert state == SkuLifecycleState.STABLE

    # Verify all transitions logged
    from sqlalchemy import select
    stmt = select(LifecycleTransitionLog).where(
        LifecycleTransitionLog.product_variant_id == variant.id
    )
    result = await db_session.execute(stmt)
    logs = list(result.scalars().all())

    assert len(logs) == 3
