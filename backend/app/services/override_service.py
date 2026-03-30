"""人工覆盖服务。"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    OverrideTargetType,
    OverrideType,
)
from app.core.logging import get_logger
from app.db.models import ManualOverride

logger = get_logger(__name__)


class OverrideService:
    """人工覆盖服务。

    允许运营人员覆盖生命周期判断或自动动作结果。

    优先级：
    1. ManualOverride（人工覆盖）
    2. ActionRule（自动规则）
    3. Default Behavior（默认行为）
    """

    def __init__(self):
        """初始化覆盖服务。"""
        pass

    async def create_override(
        self,
        db: AsyncSession,
        target_type: OverrideTargetType,
        target_id: UUID,
        override_type: OverrideType,
        override_data: dict,
        reason: str,
        created_by: str,
        effective_to: Optional[datetime] = None,
    ) -> ManualOverride:
        """创建人工覆盖。

        Args:
            db: 数据库会话
            target_type: 覆盖目标类型
            target_id: 覆盖目标 ID
            override_type: 覆盖类型
            override_data: 覆盖参数
            reason: 原因
            created_by: 创建人
            effective_to: 过期时间（可选）

        Returns:
            创建的覆盖记录
        """
        override = ManualOverride(
            id=uuid4(),
            override_type=override_type,
            target_type=target_type,
            target_id=target_id,
            override_data=override_data,
            reason=reason,
            is_active=True,
            effective_from=datetime.now(timezone.utc),
            effective_to=effective_to,
            created_by=created_by,
        )
        db.add(override)
        await db.commit()
        await db.refresh(override)

        logger.info(
            "override_created",
            override_id=str(override.id),
            target_type=target_type.value,
            target_id=str(target_id),
            override_type=override_type.value,
            created_by=created_by,
        )

        return override

    async def get_active_overrides(
        self,
        db: AsyncSession,
        target_type: Optional[OverrideTargetType] = None,
        target_id: Optional[UUID] = None,
    ) -> list[ManualOverride]:
        """获取活跃的人工覆盖。

        Args:
            db: 数据库会话
            target_type: 目标类型过滤
            target_id: 目标 ID 过滤

        Returns:
            活跃覆盖列表
        """
        now = datetime.now(timezone.utc)

        stmt = select(ManualOverride).where(
            ManualOverride.is_active == True,
            or_(
                ManualOverride.effective_to.is_(None),
                ManualOverride.effective_to > now,
            ),
            ManualOverride.effective_from <= now,
        )

        if target_type:
            stmt = stmt.where(ManualOverride.target_type == target_type)

        if target_id:
            stmt = stmt.where(ManualOverride.target_id == target_id)

        stmt = stmt.order_by(ManualOverride.effective_from.desc())

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def resolve_override_decision(
        self,
        db: AsyncSession,
        target_type: OverrideTargetType,
        target_id: UUID,
        default_decision: dict,
    ) -> dict:
        """解析覆盖决策。

        如果存在活跃的覆盖，返回覆盖后的决策；否则返回默认决策。

        Args:
            db: 数据库会话
            target_type: 目标类型
            target_id: 目标 ID
            default_decision: 默认决策

        Returns:
            覆盖后的决策
        """
        overrides = await self.get_active_overrides(
            db=db,
            target_type=target_type,
            target_id=target_id,
        )

        if not overrides:
            return {
                "overridden": False,
                "decision": default_decision,
                "override": None,
            }

        # 使用最新的覆盖
        latest_override = overrides[0]

        # 根据覆盖类型修改决策
        modified_decision = self._apply_override(
            override=latest_override,
            default_decision=default_decision,
        )

        logger.info(
            "override_applied",
            override_id=str(latest_override.id),
            target_type=target_type.value,
            target_id=str(target_id),
            override_type=latest_override.override_type.value,
        )

        return {
            "overridden": True,
            "decision": modified_decision,
            "override": latest_override,
        }

    async def cancel_override(
        self,
        db: AsyncSession,
        override_id: UUID,
        cancelled_by: str,
    ) -> bool:
        """取消覆盖。

        Args:
            db: 数据库会话
            override_id: 覆盖 ID
            cancelled_by: 取消人

        Returns:
            是否成功
        """
        stmt = select(ManualOverride).where(ManualOverride.id == override_id)
        result = await db.execute(stmt)
        override = result.scalar_one_or_none()

        if not override:
            return False

        override.is_active = False
        override.cancelled_by = cancelled_by
        override.cancelled_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info("override_cancelled", override_id=str(override_id), cancelled_by=cancelled_by)

        return True

    async def expire_override(
        self,
        db: AsyncSession,
        override_id: UUID,
    ) -> bool:
        """使覆盖过期。

        Args:
            db: 数据库会话
            override_id: 覆盖 ID

        Returns:
            是否成功
        """
        stmt = select(ManualOverride).where(ManualOverride.id == override_id)
        result = await db.execute(stmt)
        override = result.scalar_one_or_none()

        if not override:
            return False

        override.is_active = False
        override.effective_to = datetime.now(timezone.utc)
        await db.commit()

        logger.info("override_expired", override_id=str(override_id))

        return True

    def _apply_override(
        self,
        override: ManualOverride,
        default_decision: dict,
    ) -> dict:
        """应用覆盖到决策。"""
        modified = default_decision.copy()

        if override.override_type == OverrideType.ACTION_SKIP:
            modified["skip"] = True
            modified["skip_reason"] = override.reason

        elif override.override_type == OverrideType.ACTION_FORCE_EXECUTE:
            modified["force_execute"] = True
            modified["force_reason"] = override.reason

        elif override.override_type == OverrideType.STRATEGY_FREEZE:
            modified["frozen"] = True
            modified["freeze_reason"] = override.reason

        elif override.override_type == OverrideType.LIFECYCLE_STATE_OVERRIDE:
            modified["override_state"] = override.override_data.get("state")

        return modified