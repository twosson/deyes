"""Tests for OverrideService."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OverrideTargetType, OverrideType
from app.db.models import ManualOverride
from app.services.override_service import OverrideService


@pytest.mark.asyncio
async def test_create_override_basic(db_session: AsyncSession):
    """create_override should create an active override record."""
    service = OverrideService()
    target_id = uuid4()

    override = await service.create_override(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_type=OverrideType.ACTION_SKIP,
        override_data={"reason": "test"},
        reason="testing override creation",
        created_by="test_user",
    )

    assert override.id is not None
    assert override.is_active is True
    assert override.override_type == OverrideType.ACTION_SKIP
    assert override.target_type == OverrideTargetType.PLATFORM_LISTING
    assert override.target_id == target_id
    assert override.override_data == {"reason": "test"}
    assert override.reason == "testing override creation"
    assert override.created_by == "test_user"
    assert override.effective_from is not None
    assert override.effective_to is None


@pytest.mark.asyncio
async def test_create_override_with_effective_to(db_session: AsyncSession):
    """create_override should respect effective_to timestamp."""
    service = OverrideService()
    target_id = uuid4()
    effective_to = datetime.now(timezone.utc) + timedelta(hours=2)

    override = await service.create_override(
        db=db_session,
        target_type=OverrideTargetType.PRODUCT_VARIANT,
        target_id=target_id,
        override_type=OverrideType.STRATEGY_FREEZE,
        override_data={},
        reason="temp freeze",
        created_by="admin",
        effective_to=effective_to,
    )

    # SQLite strips timezone info and can alter microseconds; check the date/time parts
    assert override.effective_to.year == effective_to.year
    assert override.effective_to.month == effective_to.month
    assert override.effective_to.day == effective_to.day
    assert override.effective_to.hour == effective_to.hour
    assert override.effective_to.minute == effective_to.minute
    assert override.is_active is True


@pytest.mark.asyncio
async def test_get_active_overrides_excludes_future_override(db_session: AsyncSession):
    """get_active_overrides should not return overrides that start in the future."""
    service = OverrideService()
    target_id = uuid4()

    future_override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="future",
        is_active=True,
        effective_from=datetime.now(timezone.utc) + timedelta(hours=1),
        created_by="test_user",
    )
    db_session.add(future_override)
    await db_session.commit()

    results = await service.get_active_overrides(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
    )

    assert results == []


@pytest.mark.asyncio
async def test_get_active_overrides_excludes_expired_override(db_session: AsyncSession):
    """get_active_overrides should not return overrides past effective_to."""
    service = OverrideService()
    target_id = uuid4()

    expired_override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="expired",
        is_active=True,
        effective_from=datetime.now(timezone.utc) - timedelta(hours=5),
        effective_to=datetime.now(timezone.utc) - timedelta(hours=1),
        created_by="test_user",
    )
    db_session.add(expired_override)
    await db_session.commit()

    results = await service.get_active_overrides(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
    )

    assert results == []


@pytest.mark.asyncio
async def test_get_active_overrides_excludes_inactive_override(db_session: AsyncSession):
    """get_active_overrides should not return inactive overrides."""
    service = OverrideService()
    target_id = uuid4()

    inactive_override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="inactive",
        is_active=False,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(inactive_override)
    await db_session.commit()

    results = await service.get_active_overrides(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
    )

    assert results == []


@pytest.mark.asyncio
async def test_get_active_overrides_returns_valid_override(db_session: AsyncSession):
    """get_active_overrides should return active overrides within the time window."""
    service = OverrideService()
    target_id = uuid4()

    valid_override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="valid",
        is_active=True,
        effective_from=datetime.now(timezone.utc) - timedelta(hours=1),
        effective_to=datetime.now(timezone.utc) + timedelta(hours=1),
        created_by="test_user",
    )
    db_session.add(valid_override)
    await db_session.commit()

    results = await service.get_active_overrides(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
    )

    assert len(results) == 1
    assert results[0].reason == "valid"


@pytest.mark.asyncio
async def test_get_active_overrides_filters_by_target_type(db_session: AsyncSession):
    """get_active_overrides should filter by target_type."""
    service = OverrideService()
    id1, id2 = uuid4(), uuid4()

    override1 = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=id1,
        override_data={},
        reason="listing override",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    override2 = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.STRATEGY_FREEZE,
        target_type=OverrideTargetType.PRODUCT_VARIANT,
        target_id=id2,
        override_data={},
        reason="product override",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add_all([override1, override2])
    await db_session.commit()

    results = await service.get_active_overrides(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
    )

    assert len(results) == 1
    assert results[0].target_type == OverrideTargetType.PLATFORM_LISTING


@pytest.mark.asyncio
async def test_get_active_overrides_filters_by_target_id(db_session: AsyncSession):
    """get_active_overrides should filter by target_id."""
    service = OverrideService()
    id1, id2 = uuid4(), uuid4()

    override1 = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=id1,
        override_data={},
        reason="override 1",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    override2 = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=id2,
        override_data={},
        reason="override 2",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add_all([override1, override2])
    await db_session.commit()

    results = await service.get_active_overrides(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=id1,
    )

    assert len(results) == 1
    assert results[0].target_id == id1


@pytest.mark.asyncio
async def test_get_active_overrides_orders_by_effective_from_desc(db_session: AsyncSession):
    """get_active_overrides should return newest overrides first."""
    service = OverrideService()
    target_id = uuid4()

    older = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="older",
        is_active=True,
        effective_from=datetime.now(timezone.utc) - timedelta(hours=2),
        created_by="test_user",
    )
    newer = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="newer",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    results = await service.get_active_overrides(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
    )

    assert len(results) == 2
    assert results[0].reason == "newer"
    assert results[1].reason == "older"


@pytest.mark.asyncio
async def test_resolve_override_decision_returns_default_when_no_override(db_session: AsyncSession):
    """resolve_override_decision should return default decision when no override exists."""
    service = OverrideService()
    target_id = uuid4()
    default_decision = {"action": "publish", "state": "pending"}

    result = await service.resolve_override_decision(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        default_decision=default_decision,
    )

    assert result["overridden"] is False
    assert result["decision"] == default_decision
    assert result["override"] is None


@pytest.mark.asyncio
async def test_resolve_override_decision_applies_action_skip(db_session: AsyncSession):
    """ACTION_SKIP should add skip metadata to the default decision."""
    service = OverrideService()
    target_id = uuid4()

    override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="manual skip reason",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(override)
    await db_session.commit()

    result = await service.resolve_override_decision(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        default_decision={"action": "publish"},
    )

    assert result["overridden"] is True
    assert result["decision"]["skip"] is True
    assert result["decision"]["skip_reason"] == "manual skip reason"
    assert result["override"].id == override.id


@pytest.mark.asyncio
async def test_resolve_override_decision_applies_force_execute(db_session: AsyncSession):
    """ACTION_FORCE_EXECUTE should add force metadata to the default decision."""
    service = OverrideService()
    target_id = uuid4()

    override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_FORCE_EXECUTE,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="force publish",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(override)
    await db_session.commit()

    result = await service.resolve_override_decision(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        default_decision={"action": "skip"},
    )

    assert result["overridden"] is True
    assert result["decision"]["force_execute"] is True
    assert result["decision"]["force_reason"] == "force publish"


@pytest.mark.asyncio
async def test_resolve_override_decision_applies_strategy_freeze(db_session: AsyncSession):
    """STRATEGY_FREEZE should add frozen metadata to the default decision."""
    service = OverrideService()
    target_id = uuid4()

    override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.STRATEGY_FREEZE,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="market cooling",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(override)
    await db_session.commit()

    result = await service.resolve_override_decision(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        default_decision={"action": "continue"},
    )

    assert result["overridden"] is True
    assert result["decision"]["frozen"] is True
    assert result["decision"]["freeze_reason"] == "market cooling"


@pytest.mark.asyncio
async def test_resolve_override_decision_applies_lifecycle_state_override(db_session: AsyncSession):
    """LIFECYCLE_STATE_OVERRIDE should set override_state from override_data."""
    service = OverrideService()
    target_id = uuid4()

    override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.LIFECYCLE_STATE_OVERRIDE,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={"state": "active"},
        reason="force active",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(override)
    await db_session.commit()

    result = await service.resolve_override_decision(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        default_decision={"state": "pending"},
    )

    assert result["overridden"] is True
    assert result["decision"]["override_state"] == "active"


@pytest.mark.asyncio
async def test_resolve_override_decision_uses_newest_override(db_session: AsyncSession):
    """ManualOverride should take precedence by using the newest active override."""
    service = OverrideService()
    target_id = uuid4()

    older = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="older skip",
        is_active=True,
        effective_from=datetime.now(timezone.utc) - timedelta(hours=1),
        created_by="test_user",
    )
    newer = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_FORCE_EXECUTE,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="newer force",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    result = await service.resolve_override_decision(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        default_decision={"action": "default"},
    )

    assert result["overridden"] is True
    assert result["decision"]["force_reason"] == "newer force"
    assert "skip" not in result["decision"]


@pytest.mark.asyncio
async def test_resolve_override_decision_does_not_mutate_default_decision(db_session: AsyncSession):
    """resolve_override_decision should not mutate the caller's input dict."""
    service = OverrideService()
    target_id = uuid4()

    override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="skip",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(override)
    await db_session.commit()

    default_decision = {"action": "publish"}
    original_copy = default_decision.copy()

    await service.resolve_override_decision(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        default_decision=default_decision,
    )

    assert default_decision == original_copy


@pytest.mark.asyncio
async def test_expire_override_sets_inactive_and_effective_to(db_session: AsyncSession):
    """expire_override should set is_active to False and stamp effective_to."""
    service = OverrideService()
    target_id = uuid4()

    override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="to expire",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(override)
    await db_session.commit()

    result = await service.expire_override(db=db_session, override_id=override.id)

    assert result is True
    await db_session.refresh(override)
    assert override.is_active is False
    assert override.effective_to is not None


@pytest.mark.asyncio
async def test_expire_override_returns_false_when_missing(db_session: AsyncSession):
    """expire_override should return False when the override does not exist."""
    service = OverrideService()

    result = await service.expire_override(db=db_session, override_id=uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_cancel_override_sets_inactive_and_audit_fields(db_session: AsyncSession):
    """cancel_override should set cancellation audit fields."""
    service = OverrideService()
    target_id = uuid4()

    override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="to cancel",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(override)
    await db_session.commit()

    result = await service.cancel_override(
        db=db_session,
        override_id=override.id,
        cancelled_by="supervisor",
    )

    assert result is True
    await db_session.refresh(override)
    assert override.is_active is False
    assert override.cancelled_by == "supervisor"
    assert override.cancelled_at is not None


@pytest.mark.asyncio
async def test_cancel_override_returns_false_when_missing(db_session: AsyncSession):
    """cancel_override should return False when the override does not exist."""
    service = OverrideService()

    result = await service.cancel_override(
        db=db_session,
        override_id=uuid4(),
        cancelled_by="admin",
    )

    assert result is False


@pytest.mark.asyncio
async def test_manual_override_takes_precedence_over_default_decision(db_session: AsyncSession):
    """Priority should be ManualOverride > ActionRule > Default via resolved override output."""
    service = OverrideService()
    target_id = uuid4()

    override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.STRATEGY_FREEZE,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="freeze due to policy",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(override)
    await db_session.commit()

    default_decision = {"action": "run", "frozen": False}

    result = await service.resolve_override_decision(
        db=db_session,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        default_decision=default_decision,
    )

    assert result["overridden"] is True
    assert result["decision"]["frozen"] is True
    assert result["decision"]["freeze_reason"] == "freeze due to policy"


@pytest.mark.asyncio
async def test_all_override_types_apply_expected_decision_fields(db_session: AsyncSession):
    """Each override type should apply its expected decision field."""
    service = OverrideService()

    cases = [
        (OverrideType.LIFECYCLE_STATE_OVERRIDE, {"state": "active"}, "override_state", "active"),
        (OverrideType.ACTION_SKIP, {}, "skip", True),
        (OverrideType.ACTION_FORCE_EXECUTE, {}, "force_execute", True),
        (OverrideType.STRATEGY_FREEZE, {}, "frozen", True),
    ]

    for override_type, override_data, expected_key, expected_value in cases:
        target_id = uuid4()
        override = ManualOverride(
            id=uuid4(),
            override_type=override_type,
            target_type=OverrideTargetType.PLATFORM_LISTING,
            target_id=target_id,
            override_data=override_data,
            reason=f"test {override_type.value}",
            is_active=True,
            effective_from=datetime.now(timezone.utc),
            created_by="test_user",
        )
        db_session.add(override)
        await db_session.commit()

        result = await service.resolve_override_decision(
            db=db_session,
            target_type=OverrideTargetType.PLATFORM_LISTING,
            target_id=target_id,
            default_decision={"action": "default"},
        )

        assert result["overridden"] is True
        assert result["decision"][expected_key] == expected_value


@pytest.mark.asyncio
async def test_created_by_field_is_preserved(db_session: AsyncSession):
    """create_override should persist created_by for audit purposes."""
    service = OverrideService()
    target_id = uuid4()

    override = await service.create_override(
        db=db_session,
        target_type=OverrideTargetType.SUPPLIER,
        target_id=target_id,
        override_type=OverrideType.ACTION_SKIP,
        override_data={},
        reason="supplier flagged",
        created_by="compliance_team",
    )

    assert override.created_by == "compliance_team"


@pytest.mark.asyncio
async def test_cancel_override_persists_cancel_audit_fields(db_session: AsyncSession):
    """cancel_override should persist cancelled_by and cancelled_at."""
    service = OverrideService()
    target_id = uuid4()

    override = ManualOverride(
        id=uuid4(),
        override_type=OverrideType.ACTION_SKIP,
        target_type=OverrideTargetType.PLATFORM_LISTING,
        target_id=target_id,
        override_data={},
        reason="temp",
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        created_by="test_user",
    )
    db_session.add(override)
    await db_session.commit()

    await service.cancel_override(db=db_session, override_id=override.id, cancelled_by="manager")

    await db_session.refresh(override)
    assert override.cancelled_by == "manager"
    assert override.cancelled_at is not None
