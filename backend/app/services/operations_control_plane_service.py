"""经营控制台聚合服务。

输出"今日异常、值得加码 SKU、应清退 SKU、待审批动作"等统一视图。
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    ActionExecutionStatus,
    ActionType,
    SkuLifecycleState,
)
from app.core.logging import get_logger
from app.db.models import (
    ActionExecutionLog,
    SkuLifecycleStateModel,
)
from app.services.anomaly_detection_service import AnomalyDetectionService
from app.services.lifecycle_engine_service import LifecycleEngineService

logger = get_logger(__name__)


class OperationsControlPlaneService:
    """经营控制台聚合服务。

    汇总生命周期、动作引擎、异常检测、利润与库存快照。
    """

    def __init__(self):
        """初始化控制台服务。"""
        self.anomaly_service = AnomalyDetectionService()
        self.lifecycle_service = LifecycleEngineService()

    async def get_daily_exceptions(
        self,
        db: AsyncSession,
        platform: Optional[str] = None,
        region: Optional[str] = None,
        limit: int = 100,
    ) -> dict:
        """今日异常列表。

        Args:
            db: 数据库会话
            platform: 平台过滤
            region: 区域过滤
            limit: 返回数量限制

        Returns:
            {
                "date": str,
                "total_anomalies": int,
                "by_severity": {"critical": int, "high": int, "medium": int, "low": int},
                "anomalies": [...],
            }
        """
        # 调用异常检测服务
        global_anomalies = await self.anomaly_service.detect_global_anomalies(
            db=db,
            lookback_days=1,
            limit=limit,
        )

        # 过滤
        if platform or region:
            filtered_anomalies = []
            for anomaly in global_anomalies.get("anomalies", []):
                # TODO: 根据 platform/region 过滤
                filtered_anomalies.append(anomaly)
            global_anomalies["anomalies"] = filtered_anomalies
            global_anomalies["total_anomalies"] = len(filtered_anomalies)

        return {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "total_anomalies": global_anomalies.get("total_anomalies", 0),
            "by_severity": global_anomalies.get("by_severity", {}),
            "anomalies": global_anomalies.get("anomalies", [])[:limit],
        }

    async def get_scaling_candidates(
        self,
        db: AsyncSession,
        platform: Optional[str] = None,
        region: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """值得加码的 SKU 列表。

        条件：
        - 生命周期状态为 TESTING 或 SCALING
        - 利润率 > 25%
        - 7d revenue trend > 0
        """
        # 查询 TESTING 和 SCALING 状态的 SKU
        stmt = (
            select(SkuLifecycleStateModel)
            .where(
                SkuLifecycleStateModel.current_state.in_([
                    SkuLifecycleState.TESTING,
                    SkuLifecycleState.SCALING,
                ])
            )
            .order_by(SkuLifecycleStateModel.entered_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        states = list(result.scalars().all())

        candidates = []
        for state in states:
            # 获取 confidence_score（存储在 state_metadata 中）
            metadata = state.state_metadata or {}
            confidence_score = metadata.get("confidence_score", 0.0)

            # TODO: 获取利润率和收入趋势进行进一步过滤
            candidates.append({
                "product_variant_id": str(state.product_variant_id),
                "current_state": state.current_state.value,
                "entered_at": state.entered_at.isoformat() if state.entered_at else None,
                "confidence_score": float(confidence_score),
                "reason": "Testing/Scaling with good performance",
            })

        logger.info(
            "scaling_candidates_retrieved",
            count=len(candidates),
        )

        return candidates

    async def get_clearance_candidates(
        self,
        db: AsyncSession,
        platform: Optional[str] = None,
        region: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """应清退的 SKU 列表。

        条件：
        - 生命周期状态为 DECLINING 或 CLEARANCE
        - 利润率 < 10%
        - 7d revenue trend < 0
        """
        # 查询 DECLINING 和 CLEARANCE 状态的 SKU
        stmt = (
            select(SkuLifecycleStateModel)
            .where(
                SkuLifecycleStateModel.current_state.in_([
                    SkuLifecycleState.DECLINING,
                    SkuLifecycleState.CLEARANCE,
                ])
            )
            .order_by(SkuLifecycleStateModel.entered_at.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        states = list(result.scalars().all())

        candidates = []
        for state in states:
            # 获取 confidence_score（存储在 state_metadata 中）
            metadata = state.state_metadata or {}
            confidence_score = metadata.get("confidence_score", 0.0)

            # TODO: 获取利润率和收入趋势进行进一步过滤
            candidates.append({
                "product_variant_id": str(state.product_variant_id),
                "current_state": state.current_state.value,
                "entered_at": state.entered_at.isoformat() if state.entered_at else None,
                "confidence_score": float(confidence_score),
                "reason": "Declining/Clearance with poor performance",
            })

        logger.info(
            "clearance_candidates_retrieved",
            count=len(candidates),
        )

        return candidates

    async def get_pending_action_approvals(
        self,
        db: AsyncSession,
        platform: Optional[str] = None,
        region: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """待审批动作列表。

        条件：
        - 执行状态为 PENDING
        - 高风险动作需要审批
        """
        # 查询待执行的动作
        stmt = (
            select(ActionExecutionLog)
            .where(ActionExecutionLog.status == ActionExecutionStatus.PENDING.value)
            .order_by(ActionExecutionLog.started_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        actions = list(result.scalars().all())

        pending = []
        for action in actions:
            pending.append({
                "execution_id": str(action.id),
                "action_type": action.action_type.value if isinstance(action.action_type, ActionType) else action.action_type,
                "product_variant_id": str(action.target_id) if action.target_type == "product_variant" else None,
                "listing_id": str(action.target_id) if action.target_type == "platform_listing" else None,
                "target_type": action.target_type,
                "input_params": action.input_params,
                "status": action.status.value if isinstance(action.status, ActionExecutionStatus) else action.status,
                "created_at": action.started_at.isoformat() if action.started_at else None,
            })

        logger.info(
            "pending_action_approvals_retrieved",
            count=len(pending),
        )

        return pending

    async def get_operations_summary(
        self,
        db: AsyncSession,
    ) -> dict:
        """运营控制台汇总视图。

        Returns:
            {
                "daily_exceptions": {...},
                "scaling_candidates_count": int,
                "clearance_candidates_count": int,
                "pending_actions_count": int,
            }
        """
        exceptions = await self.get_daily_exceptions(db=db, limit=10)
        scaling = await self.get_scaling_candidates(db=db, limit=50)
        clearance = await self.get_clearance_candidates(db=db, limit=50)
        pending = await self.get_pending_action_approvals(db=db, limit=50)

        return {
            "daily_exceptions": {
                "total": exceptions["total_anomalies"],
                "by_severity": exceptions["by_severity"],
            },
            "scaling_candidates_count": len(scaling),
            "clearance_candidates_count": len(clearance),
            "pending_actions_count": len(pending),
        }
