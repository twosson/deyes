"""Tests for action engine service."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    ActionExecutionStatus,
    ActionType,
    PlatformListingStatus,
    ProductVariantStatus,
    SkuLifecycleState,
)
from app.db.models import (
    ActionExecutionLog,
    ActionRule,
    ListingAssetAssociation,
    PlatformListing,
    PriceHistory,
    ProductMaster,
    ProductVariant,
    ProfitLedger,
    SkuLifecycleStateModel,
)
from app.services.action_engine_service import ActionEngineService


async def _create_product_variant(db_session: AsyncSession, suffix: str = "001") -> ProductVariant:
    """Create a product variant for testing."""
    master = ProductMaster(
        id=uuid4(),
        internal_sku=f"TEST-MASTER-{suffix}",
        name="Test Product",
    )
    db_session.add(master)

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku=f"TEST-SKU-{suffix}",
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(variant)
    return variant


async def _create_execution_log(
    db_session: AsyncSession,
    action_type: ActionType,
    target_id,
    status: ActionExecutionStatus = ActionExecutionStatus.PENDING,
    input_params: Optional[dict] = None,
    output_data: Optional[dict] = None,
) -> ActionExecutionLog:
    """Create an action execution log for approval/rollback tests."""
    execution = ActionExecutionLog(
        id=uuid4(),
        action_type=action_type,
        target_type="product_variant",
        target_id=target_id,
        status=status,
        started_at=datetime.now(timezone.utc),
        input_params=input_params,
        output_data=output_data,
    )
    db_session.add(execution)
    await db_session.commit()
    await db_session.refresh(execution)
    return execution


@pytest.mark.asyncio
async def test_check_safety_constraints_allows_repricing_within_20_percent(db_session: AsyncSession):
    """ActionEngineService should allow repricing within ±20% threshold."""
    service = ActionEngineService()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.REPRICING,
        product_variant_id=None,
        payload={"price_change_percentage": Decimal("0.20")},
    )

    assert result["allowed"] is True
    assert result["risk_level"] == service.RISK_LOW
    assert result["requires_approval"] is False


@pytest.mark.asyncio
async def test_check_safety_constraints_rejects_repricing_beyond_20_percent(db_session: AsyncSession):
    """ActionEngineService should reject repricing beyond ±20% threshold."""
    service = ActionEngineService()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.REPRICING,
        product_variant_id=None,
        payload={"price_change_percentage": Decimal("0.21")},
    )

    assert result["allowed"] is False
    assert "exceeds max" in result["reason"]
    assert result["risk_level"] == service.RISK_HIGH
    assert result["requires_approval"] is True


@pytest.mark.asyncio
async def test_check_safety_constraints_accepts_numeric_repricing_input(db_session: AsyncSession):
    """ActionEngineService should convert numeric repricing input to Decimal."""
    service = ActionEngineService()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.REPRICING,
        product_variant_id=None,
        payload={"price_change_percentage": 0.15},
    )

    assert result["allowed"] is True
    assert result["requires_approval"] is False


@pytest.mark.asyncio
async def test_check_safety_constraints_allows_replenish_within_30_day_sales(db_session: AsyncSession):
    """ActionEngineService should allow replenish within 30-day sales volume."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "101")

    # Create 30-day sales history totaling 100 orders (100 ledger records)
    for i in range(100):
        ledger = ProfitLedger(
            id=uuid4(),
            product_variant_id=variant.id,
            snapshot_date=date.today() - timedelta(days=5),
            gross_revenue=Decimal("10.00"),
            net_profit=Decimal("3.00"),
        )
        db_session.add(ledger)
    await db_session.commit()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.REPLENISH,
        product_variant_id=variant.id,
        payload={"quantity": 100},
    )

    assert result["allowed"] is True
    assert result["requires_approval"] is False


@pytest.mark.asyncio
async def test_check_safety_constraints_rejects_replenish_above_30_day_sales(db_session: AsyncSession):
    """ActionEngineService should reject replenish above 30-day sales volume."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "102")

    # Create 30-day sales history totaling 50 orders (50 ledger records)
    for i in range(50):
        ledger = ProfitLedger(
            id=uuid4(),
            product_variant_id=variant.id,
            snapshot_date=date.today() - timedelta(days=10),
            gross_revenue=Decimal("10.00"),
            net_profit=Decimal("3.00"),
        )
        db_session.add(ledger)
    await db_session.commit()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.REPLENISH,
        product_variant_id=variant.id,
        payload={"quantity": 51},
    )

    assert result["allowed"] is False
    assert "exceeds max 50" in result["reason"]
    assert result["risk_level"] == service.RISK_MEDIUM
    assert result["requires_approval"] is True


@pytest.mark.asyncio
async def test_check_safety_constraints_allows_delist_for_declining_state(db_session: AsyncSession):
    """ActionEngineService should allow delist when variant is in declining state."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "103")

    state_record = SkuLifecycleStateModel(
        id=uuid4(),
        product_variant_id=variant.id,
        current_state=SkuLifecycleState.DECLINING,
        entered_at=datetime.now(timezone.utc) - timedelta(days=14),
    )
    db_session.add(state_record)
    await db_session.commit()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.DELIST,
        product_variant_id=variant.id,
        payload={},
    )

    assert result["allowed"] is True
    assert result["requires_approval"] is False


@pytest.mark.asyncio
async def test_check_safety_constraints_rejects_delist_for_non_declining_state(db_session: AsyncSession):
    """ActionEngineService should reject delist when variant is not declining or clearance."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "104")

    state_record = SkuLifecycleStateModel(
        id=uuid4(),
        product_variant_id=variant.id,
        current_state=SkuLifecycleState.STABLE,
        entered_at=datetime.now(timezone.utc) - timedelta(days=14),
    )
    db_session.add(state_record)
    await db_session.commit()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.DELIST,
        product_variant_id=variant.id,
        payload={},
    )

    assert result["allowed"] is False
    assert "not declining/clearance" in result["reason"]
    assert result["risk_level"] == service.RISK_HIGH
    assert result["requires_approval"] is True


@pytest.mark.asyncio
async def test_check_safety_constraints_allows_expand_platform_with_margin_and_stable_days(db_session: AsyncSession):
    """ActionEngineService should allow expand platform when thresholds are met."""
    service = ActionEngineService()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.EXPAND_PLATFORM,
        product_variant_id=None,
        payload={"margin": Decimal("0.30"), "stable_days": 30},
    )

    assert result["allowed"] is True
    assert result["requires_approval"] is False


@pytest.mark.asyncio
async def test_check_safety_constraints_rejects_expand_platform_below_thresholds(db_session: AsyncSession):
    """ActionEngineService should reject expand platform below margin and stable-day thresholds."""
    service = ActionEngineService()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.EXPAND_PLATFORM,
        product_variant_id=None,
        payload={"margin": Decimal("0.25"), "stable_days": 20},
    )

    assert result["allowed"] is False
    assert "margin 25.0% below min 30.0%" in result["reason"]
    assert "stable days 20 below min 30" in result["reason"]
    assert result["risk_level"] == service.RISK_MEDIUM
    assert result["requires_approval"] is True


@pytest.mark.asyncio
async def test_check_safety_constraints_requires_approval_for_retire(db_session: AsyncSession):
    """ActionEngineService should always require approval for retire action."""
    service = ActionEngineService()

    result = await service._check_safety_constraints(
        db=db_session,
        action_type=ActionType.RETIRE,
        product_variant_id=None,
        payload={},
    )

    assert result["allowed"] is True
    assert result["risk_level"] == service.RISK_HIGH
    assert result["requires_approval"] is True


@pytest.mark.asyncio
async def test_evaluate_actions_combines_action_candidates(db_session: AsyncSession):
    """ActionEngineService should combine actions from all evaluators."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "105")

    async def mock_repricing(_db, _variant_id):
        return [{"action_type": ActionType.REPRICING, "trigger_reason": "low margin"}]

    async def mock_replenish(_db, _variant_id):
        return [{"action_type": ActionType.REPLENISH, "trigger_reason": "low stock"}]

    async def mock_delist(_db, _variant_id):
        return [{"action_type": ActionType.DELIST, "trigger_reason": "declining"}]

    service._evaluate_repricing = mock_repricing
    service._evaluate_replenish = mock_replenish
    service._evaluate_delist = mock_delist

    actions = await service.evaluate_actions(db_session, variant.id)

    assert len(actions) == 3
    assert {action["action_type"] for action in actions} == {
        ActionType.REPRICING,
        ActionType.REPLENISH,
        ActionType.DELIST,
    }


@pytest.mark.asyncio
async def test_execute_action_with_mode_returns_dry_run_without_persisting_log(db_session: AsyncSession):
    """ActionEngineService should return dry-run result without executing action."""
    service = ActionEngineService()

    result = await service.execute_action_with_mode(
        db=db_session,
        action_type=ActionType.REPRICING,
        payload={"price_change_percentage": Decimal("0.10")},
        execution_mode=service.EXECUTION_MODE_DRY_RUN,
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["action_type"] == ActionType.REPRICING.value

    stmt = select(ActionExecutionLog)
    db_result = await db_session.execute(stmt)
    assert list(db_result.scalars().all()) == []


@pytest.mark.asyncio
async def test_execute_action_with_mode_returns_suggestion_without_persisting_log(db_session: AsyncSession):
    """ActionEngineService should return suggestion result without executing action."""
    service = ActionEngineService()

    result = await service.execute_action_with_mode(
        db=db_session,
        action_type=ActionType.REPLENISH,
        payload={"quantity": 20},
        execution_mode=service.EXECUTION_MODE_SUGGEST,
    )

    assert result["success"] is True
    assert result["suggest"] is True
    assert result["action_type"] == ActionType.REPLENISH.value

    stmt = select(ActionExecutionLog)
    db_result = await db_session.execute(stmt)
    assert list(db_result.scalars().all()) == []


@pytest.mark.asyncio
async def test_execute_action_with_mode_rejects_unsafe_action_and_logs_cancellation(db_session: AsyncSession):
    """ActionEngineService should reject unsafe action and persist cancelled log."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "106")

    result = await service.execute_action_with_mode(
        db=db_session,
        action_type=ActionType.REPRICING,
        product_variant_id=variant.id,
        payload={"price_change_percentage": Decimal("0.25")},
        execution_mode=service.EXECUTION_MODE_AUTO,
    )

    assert result["success"] is False
    assert result["rejected"] is True
    assert result["risk_level"] == service.RISK_HIGH

    stmt = select(ActionExecutionLog).where(ActionExecutionLog.target_id == variant.id)
    db_result = await db_session.execute(stmt)
    execution = db_result.scalar_one()
    assert execution.status == ActionExecutionStatus.CANCELLED
    assert execution.output_data["rejected"] is True


@pytest.mark.asyncio
async def test_execute_action_creates_completed_log_for_listing_target(db_session: AsyncSession, sample_active_listing: PlatformListing):
    """ActionEngineService should create completed execution log for listing-targeted action."""
    service = ActionEngineService()

    result = await service.execute_action(
        db=db_session,
        action_type=ActionType.REPRICING,
        listing_id=sample_active_listing.id,
        payload={"price_change_percentage": Decimal("0.10")},
    )

    assert result["success"] is True
    assert "execution_id" in result

    stmt = select(ActionExecutionLog).where(ActionExecutionLog.id == result["execution_id"])
    db_result = await db_session.execute(stmt)
    execution = db_result.scalar_one()

    assert execution.target_type == "platform_listing"
    assert execution.target_id == sample_active_listing.id
    assert execution.status == ActionExecutionStatus.COMPLETED
    assert execution.output_data["executed"] is True


@pytest.mark.asyncio
async def test_execute_action_records_failure_when_execution_raises(db_session: AsyncSession):
    """ActionEngineService should record failed status when execution raises."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "107")

    async def mock_do_execute(**_kwargs):
        raise RuntimeError("boom")

    service._do_execute = mock_do_execute

    result = await service.execute_action(
        db=db_session,
        action_type=ActionType.REPLENISH,
        product_variant_id=variant.id,
        payload={"quantity": 10},
    )

    assert result["success"] is False
    assert "failed: boom" in result["message"]

    stmt = select(ActionExecutionLog).where(ActionExecutionLog.id == result["execution_id"])
    db_result = await db_session.execute(stmt)
    execution = db_result.scalar_one()
    assert execution.status == ActionExecutionStatus.FAILED
    assert execution.error_message == "boom"


@pytest.mark.asyncio
async def test_approve_action_marks_pending_execution_approved(db_session: AsyncSession):
    """ActionEngineService should approve pending execution."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "108")
    execution = await _create_execution_log(db_session, ActionType.RETIRE, variant.id)

    result = await service.approve_action(
        db=db_session,
        execution_id=execution.id,
        approved_by="operator@example.com",
        comment="approved for cleanup",
    )

    assert result["success"] is True

    refreshed = await db_session.get(ActionExecutionLog, execution.id)
    assert refreshed.status == ActionExecutionStatus.APPROVED
    assert refreshed.approved_by == "operator@example.com"
    assert refreshed.output_data["approval_action"] == "approved"
    assert refreshed.output_data["approval_comment"] == "approved for cleanup"


@pytest.mark.asyncio
async def test_reject_action_marks_pending_approval_execution_rejected(db_session: AsyncSession):
    """ActionEngineService should reject pending-approval execution."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "109")
    execution = await _create_execution_log(
        db_session,
        ActionType.REPLENISH,
        variant.id,
        status=ActionExecutionStatus.PENDING_APPROVAL,
    )

    result = await service.reject_action(
        db=db_session,
        execution_id=execution.id,
        rejected_by="reviewer@example.com",
        comment="quantity too high",
    )

    assert result["success"] is True

    refreshed = await db_session.get(ActionExecutionLog, execution.id)
    assert refreshed.status == ActionExecutionStatus.REJECTED
    assert refreshed.approved_by == "reviewer@example.com"
    assert refreshed.output_data["approval_action"] == "rejected"
    assert refreshed.output_data["rejection_comment"] == "quantity too high"


@pytest.mark.asyncio
async def test_defer_action_marks_pending_execution_deferred(db_session: AsyncSession):
    """ActionEngineService should defer pending execution."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "110")
    execution = await _create_execution_log(db_session, ActionType.DELIST, variant.id)

    result = await service.defer_action(
        db=db_session,
        execution_id=execution.id,
        deferred_by="reviewer@example.com",
        comment="wait for more data",
    )

    assert result["success"] is True

    refreshed = await db_session.get(ActionExecutionLog, execution.id)
    assert refreshed.status == ActionExecutionStatus.DEFERRED
    assert refreshed.approved_by == "reviewer@example.com"
    assert refreshed.output_data["approval_action"] == "deferred"
    assert refreshed.output_data["defer_comment"] == "wait for more data"


@pytest.mark.asyncio
async def test_approve_action_rejects_non_pending_status(db_session: AsyncSession):
    """ActionEngineService should reject approval for non-pending execution."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "111")
    execution = await _create_execution_log(
        db_session,
        ActionType.REPRICING,
        variant.id,
        status=ActionExecutionStatus.COMPLETED,
    )

    result = await service.approve_action(
        db=db_session,
        execution_id=execution.id,
        approved_by="operator@example.com",
    )

    assert result["success"] is False
    assert "Cannot approve action in status completed" == result["message"]


@pytest.mark.asyncio
async def test_approve_action_returns_not_found_for_missing_execution(db_session: AsyncSession):
    """ActionEngineService should return not found for missing execution during approval."""
    service = ActionEngineService()

    result = await service.approve_action(
        db=db_session,
        execution_id=uuid4(),
        approved_by="operator@example.com",
    )

    assert result["success"] is False
    assert "not found" in result["message"]


@pytest.mark.asyncio
async def test_rollback_action_restores_previous_price_and_creates_history(db_session: AsyncSession, sample_active_listing: PlatformListing):
    """ActionEngineService should rollback repricing by restoring previous price and writing history."""
    service = ActionEngineService()

    sample_active_listing.price = Decimal("55.00")
    await db_session.commit()

    execution = await _create_execution_log(
        db_session,
        ActionType.REPRICING,
        sample_active_listing.id,
        status=ActionExecutionStatus.COMPLETED,
        input_params={
            "rollback": {
                "listing_id": str(sample_active_listing.id),
                "previous_price": "50.00",
                "previous_currency": "USD",
            }
        },
    )

    result = await service.rollback_action(
        db=db_session,
        action_execution_id=execution.id,
        rolled_back_by="operator@example.com",
        reason="manual correction",
    )

    assert result["success"] is True
    assert result["rollback_result"]["restored_price"] == "50.00"

    refreshed_listing = await db_session.get(PlatformListing, sample_active_listing.id)
    assert refreshed_listing.price == Decimal("50.00")

    refreshed_execution = await db_session.get(ActionExecutionLog, execution.id)
    assert refreshed_execution.status == ActionExecutionStatus.ROLLED_BACK
    assert refreshed_execution.output_data["rollback"]["action_type"] == ActionType.REPRICING.value

    stmt = select(PriceHistory).where(PriceHistory.listing_id == sample_active_listing.id)
    db_result = await db_session.execute(stmt)
    history = db_result.scalar_one()
    assert history.old_price == Decimal("55.00")
    assert history.new_price == Decimal("50.00")
    assert history.changed_by == "operator@example.com"


@pytest.mark.asyncio
async def test_rollback_action_restores_previous_listing_status(db_session: AsyncSession, sample_active_listing: PlatformListing):
    """ActionEngineService should rollback delist by restoring listing status."""
    service = ActionEngineService()

    sample_active_listing.status = PlatformListingStatus.DELISTED
    await db_session.commit()

    execution = await _create_execution_log(
        db_session,
        ActionType.DELIST,
        sample_active_listing.id,
        status=ActionExecutionStatus.COMPLETED,
        input_params={
            "rollback": {
                "listing_id": str(sample_active_listing.id),
                "previous_status": PlatformListingStatus.ACTIVE.value,
            }
        },
    )

    result = await service.rollback_action(
        db=db_session,
        action_execution_id=execution.id,
        rolled_back_by="operator@example.com",
        reason="restore listing",
    )

    assert result["success"] is True
    assert result["rollback_result"]["restored_status"] == PlatformListingStatus.ACTIVE.value

    refreshed_listing = await db_session.get(PlatformListing, sample_active_listing.id)
    assert refreshed_listing.status == PlatformListingStatus.ACTIVE


@pytest.mark.asyncio
async def test_rollback_action_restores_previous_main_asset(db_session: AsyncSession, sample_active_listing: PlatformListing):
    """ActionEngineService should rollback swap_content by restoring previous main asset."""
    service = ActionEngineService()

    previous_asset_id = uuid4()
    current_asset_id = uuid4()

    current_assoc = ListingAssetAssociation(
        listing_id=sample_active_listing.id,
        asset_id=current_asset_id,
        display_order=0,
        is_main=True,
    )
    db_session.add(current_assoc)
    await db_session.commit()

    execution = await _create_execution_log(
        db_session,
        ActionType.SWAP_CONTENT,
        sample_active_listing.id,
        status=ActionExecutionStatus.COMPLETED,
        input_params={
            "rollback": {
                "listing_id": str(sample_active_listing.id),
                "previous_main_asset_id": str(previous_asset_id),
            }
        },
    )

    result = await service.rollback_action(
        db=db_session,
        action_execution_id=execution.id,
        rolled_back_by="operator@example.com",
        reason="bad creative",
    )

    assert result["success"] is True
    assert result["rollback_result"]["restored_main_asset_id"] == str(previous_asset_id)

    stmt = select(ListingAssetAssociation).where(
        ListingAssetAssociation.listing_id == sample_active_listing.id,
        ListingAssetAssociation.is_main.is_(True),
    )
    db_result = await db_session.execute(stmt)
    assoc = db_result.scalar_one()
    assert assoc.asset_id == previous_asset_id


@pytest.mark.asyncio
async def test_rollback_action_rejects_non_rollbackable_action(db_session: AsyncSession):
    """ActionEngineService should reject rollback for non-rollbackable action types."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "112")
    execution = await _create_execution_log(
        db_session,
        ActionType.REPLENISH,
        variant.id,
        status=ActionExecutionStatus.COMPLETED,
        input_params={"rollback": {"quantity": 10}},
    )

    result = await service.rollback_action(
        db=db_session,
        action_execution_id=execution.id,
        rolled_back_by="operator@example.com",
        reason="cannot undo PO",
    )

    assert result["success"] is False
    assert "not rollbackable" in result["message"]
    assert result["rollback_result"]["rollbackable"] is False

    refreshed = await db_session.get(ActionExecutionLog, execution.id)
    assert refreshed.status == ActionExecutionStatus.COMPLETED
    assert refreshed.output_data["rollback_attempt"]["rollbackable"] is False


@pytest.mark.asyncio
async def test_rollback_action_rejects_missing_context(db_session: AsyncSession):
    """ActionEngineService should reject rollback when no rollback context exists."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "113")
    execution = await _create_execution_log(
        db_session,
        ActionType.REPRICING,
        variant.id,
        status=ActionExecutionStatus.COMPLETED,
        input_params={},
    )

    result = await service.rollback_action(
        db=db_session,
        action_execution_id=execution.id,
        rolled_back_by="operator@example.com",
        reason="missing metadata",
    )

    assert result["success"] is False
    assert "No rollback context recorded" in result["message"]
    assert result["rollback_result"]["rollbackable"] is False


@pytest.mark.asyncio
async def test_rollback_action_rejects_non_completed_status(db_session: AsyncSession):
    """ActionEngineService should reject rollback when action is not completed."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "114")
    execution = await _create_execution_log(
        db_session,
        ActionType.REPRICING,
        variant.id,
        status=ActionExecutionStatus.PENDING,
    )

    result = await service.rollback_action(
        db=db_session,
        action_execution_id=execution.id,
    )

    assert result["success"] is False
    assert "Cannot rollback action in status pending" == result["message"]


@pytest.mark.asyncio
async def test_load_active_rules_filters_and_orders_by_priority(db_session: AsyncSession):
    """ActionEngineService should load active rules filtered by action type and sorted by priority."""
    service = ActionEngineService()

    rule_low = ActionRule(
        id=uuid4(),
        rule_name="repricing-low",
        action_type=ActionType.REPRICING,
        trigger_conditions={"margin_below": 0.1},
        action_params={"price_change_percentage": -0.05},
        priority=10,
        is_active=True,
    )
    rule_high = ActionRule(
        id=uuid4(),
        rule_name="repricing-high",
        action_type=ActionType.REPRICING,
        trigger_conditions={"margin_below": 0.05},
        action_params={"price_change_percentage": -0.10},
        priority=20,
        is_active=True,
    )
    rule_other = ActionRule(
        id=uuid4(),
        rule_name="replenish-rule",
        action_type=ActionType.REPLENISH,
        trigger_conditions={"coverage_days_below": 7},
        action_params={"quantity": 100},
        priority=99,
        is_active=True,
    )
    rule_inactive = ActionRule(
        id=uuid4(),
        rule_name="inactive-rule",
        action_type=ActionType.REPRICING,
        trigger_conditions={"margin_below": 0.2},
        action_params={"price_change_percentage": -0.02},
        priority=30,
        is_active=False,
    )
    db_session.add_all([rule_low, rule_high, rule_other, rule_inactive])
    await db_session.commit()

    rules = await service.load_active_rules(db_session, action_type=ActionType.REPRICING)

    assert [rule.rule_name for rule in rules] == ["repricing-high", "repricing-low"]


@pytest.mark.asyncio
async def test_get_pending_actions_filters_by_target_and_type(db_session: AsyncSession):
    """ActionEngineService should filter pending actions by target and action type."""
    service = ActionEngineService()
    variant = await _create_product_variant(db_session, "115")
    other_variant = await _create_product_variant(db_session, "116")

    pending_match = await _create_execution_log(
        db_session,
        ActionType.REPRICING,
        variant.id,
        status=ActionExecutionStatus.PENDING,
    )
    await _create_execution_log(
        db_session,
        ActionType.REPLENISH,
        variant.id,
        status=ActionExecutionStatus.PENDING,
    )
    await _create_execution_log(
        db_session,
        ActionType.REPRICING,
        other_variant.id,
        status=ActionExecutionStatus.PENDING,
    )
    await _create_execution_log(
        db_session,
        ActionType.REPRICING,
        variant.id,
        status=ActionExecutionStatus.COMPLETED,
    )

    actions = await service.get_pending_actions(
        db=db_session,
        product_variant_id=variant.id,
        action_type=ActionType.REPRICING,
    )

    assert len(actions) == 1
    assert actions[0].id == pending_match.id
