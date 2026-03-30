"""SKU 生命周期引擎服务。"""
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SkuLifecycleState
from app.core.logging import get_logger
from app.db.models import (
    LifecycleRule,
    LifecycleTransitionLog,
    SkuLifecycleStateModel,
)

logger = get_logger(__name__)


class LifecycleEngineService:
    """SKU 生命周期引擎。

    根据经营结果和规则判断 SKU 当前所处阶段。

    状态机：
    DISCOVERING → TESTING → SCALING → STABLE → DECLINING → CLEARANCE → RETIRED

    状态迁移规则：
    - DISCOVERING → TESTING: 上架第一个 listing
    - TESTING → SCALING: 7d revenue > 1000 AND 7d margin > 20%
    - SCALING → STABLE: 连续 14 天 SCALING 状态
    - STABLE → DECLINING: 7d revenue drop > 30% OR 7d margin < 10%
    - DECLINING → CLEARANCE: 连续 14 天 DECLINING 状态
    - DECLINING → STABLE: 如果恢复（recover）
    - CLEARANCE → RETIRED: 手动或自动触发
    """

    def __init__(self):
        """初始化生命周期引擎。"""
        pass

    async def evaluate_state(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
    ) -> dict:
        """评估 SKU 当前生命周期状态。

        Args:
            db: 数据库会话
            product_variant_id: SKU ID

        Returns:
            {
                "current_state": SkuLifecycleState,
                "confidence_score": float,
                "reasons": [str],
                "should_transition": bool,
                "suggested_next_state": Optional[SkuLifecycleState],
            }
        """
        # 获取当前状态
        current_state = await self.get_current_state(db, product_variant_id)

        # 获取生命周期信号
        from app.services.lifecycle_signal_service import LifecycleSignalService
        signal_service = LifecycleSignalService()
        signals = await signal_service.get_signal_snapshot(db, product_variant_id)

        # 评估是否应该迁移
        # TODO: 实现状态迁移评估逻辑

        return {
            "current_state": current_state,
            "confidence_score": 1.0,
            "reasons": [],
            "should_transition": False,
            "suggested_next_state": None,
        }

    async def apply_transition(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        target_state: SkuLifecycleState,
        reason: str,
        trigger_source: str = "lifecycle_engine",
        trigger_payload: Optional[dict] = None,
    ) -> bool:
        """应用状态迁移。

        Args:
            db: 数据库会话
            product_variant_id: SKU ID
            target_state: 目标状态
            reason: 迁移原因
            trigger_source: 触发来源
            trigger_payload: 触发参数

        Returns:
            是否迁移成功
        """
        # 获取当前状态
        current_state = await self.get_current_state(db, product_variant_id)

        if current_state == target_state:
            logger.info("lifecycle_state_no_change", product_variant_id=str(product_variant_id), state=current_state.value)
            return False

        # 创建或更新状态记录
        state_record = await self._get_or_create_state(db, product_variant_id)
        state_record.current_state = target_state
        state_record.entered_at = datetime.now(timezone.utc)

        # Store reason in state_metadata since there's no direct reason field
        metadata = dict(state_record.state_metadata or {})
        metadata["reason"] = reason
        state_record.state_metadata = metadata

        await db.flush()

        # 记录迁移日志
        log_entry = LifecycleTransitionLog(
            id=uuid4(),
            product_variant_id=product_variant_id,
            from_state=current_state,
            to_state=target_state,
            transitioned_at=datetime.now(timezone.utc),
            triggered_by=trigger_source,
            trigger_data=trigger_payload or {},
        )
        db.add(log_entry)

        await db.commit()

        logger.info(
            "lifecycle_state_transitioned",
            product_variant_id=str(product_variant_id),
            from_state=current_state.value,
            to_state=target_state.value,
            reason=reason,
        )

        return True

    async def get_current_state(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
    ) -> SkuLifecycleState:
        """获取 SKU 当前生命周期状态。

        Args:
            db: 数据库会话
            product_variant_id: SKU ID

        Returns:
            当前生命周期状态，默认为 DISCOVERING
        """
        stmt = select(SkuLifecycleStateModel).where(
            SkuLifecycleStateModel.product_variant_id == product_variant_id
        )
        result = await db.execute(stmt)
        state_record = result.scalar_one_or_none()

        if state_record:
            return state_record.current_state

        return SkuLifecycleState.DISCOVERING

    async def load_rules(self, db: AsyncSession) -> list[LifecycleRule]:
        """加载生命周期规则。"""
        stmt = select(LifecycleRule).where(LifecycleRule.is_active == True)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _get_or_create_state(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
    ) -> SkuLifecycleStateModel:
        """获取或创建生命周期状态记录。"""
        stmt = select(SkuLifecycleStateModel).where(
            SkuLifecycleStateModel.product_variant_id == product_variant_id
        )
        result = await db.execute(stmt)
        state_record = result.scalar_one_or_none()

        if not state_record:
            state_record = SkuLifecycleStateModel(
                id=uuid4(),
                product_variant_id=product_variant_id,
                current_state=SkuLifecycleState.DISCOVERING,
                entered_at=datetime.now(timezone.utc),
                state_metadata={"confidence_score": 1.0},
            )
            db.add(state_record)
            await db.flush()

        return state_record
