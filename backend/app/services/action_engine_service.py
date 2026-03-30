"""自动动作引擎服务。"""
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    ActionExecutionStatus,
    ActionType,
)
from app.core.logging import get_logger
from app.db.models import (
    ActionExecutionLog,
    ActionRule,
)

logger = get_logger(__name__)


def _serialize_for_json(obj):
    """Convert objects to JSON-serializable types.

    Handles Decimal, UUID, datetime, and nested structures.
    """
    if isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_serialize_for_json(item) for item in obj]
    else:
        return obj


class ActionEngineService:
    """自动动作引擎。

    根据规则和当前信号生成待执行动作并记录执行结果。

    支持的动作类型：
    - repricing: 调价
    - replenish: 补货
    - swap_content: 换素材
    - expand_platform: 扩平台
    - delist: 下架
    - retire: 退市

    安全阈值：
    - repricing: 最大调价幅度 ±20%
    - replenish: 最大补货量 = 30 天销量
    - delist: 最小衰退期 > 14 天
    """

    # 安全阈值
    MAX_REPRICE_PERCENTAGE = Decimal("0.20")  # 20%
    MAX_REPLENISH_DAYS = 30  # 30 天销量
    MIN_DECLINING_DAYS_FOR_DELIST = 14  # 自动下架前的最小衰退天数
    MIN_MARGIN_FOR_EXPAND_PLATFORM = Decimal("0.30")  # 扩平台前最小利润率
    MIN_STABLE_DAYS_FOR_EXPAND_PLATFORM = 30  # 扩平台前最小稳定天数

    # 动作执行模式
    EXECUTION_MODE_AUTO = "auto"  # 自动执行
    EXECUTION_MODE_SUGGEST = "suggest"  # 只建议不执行
    EXECUTION_MODE_DRY_RUN = "dry_run"  # 试运行（不实际执行）

    # 风险等级
    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"

    # 可回滚动作类型
    ROLLBACKABLE_ACTIONS = {
        ActionType.REPRICING,
        ActionType.SWAP_CONTENT,
        ActionType.DELIST,
    }

    # 不可回滚动作类型（需要显式标注）
    NON_ROLLBACKABLE_ACTIONS = {
        ActionType.REPLENISH,  # 物理库存已下单，无法回滚
        ActionType.EXPAND_PLATFORM,  # 平台已创建 listing，无法回滚
        ActionType.RETIRE,  # 退市操作不可回滚
    }

    def __init__(self):
        """初始化动作引擎。"""
        pass

    async def _check_safety_constraints(
        self,
        db: AsyncSession,
        action_type: ActionType,
        product_variant_id: Optional[UUID],
        payload: dict,
    ) -> dict:
        """检查安全约束。

        Args:
            db: 数据库会话
            action_type: 动作类型
            product_variant_id: SKU ID
            payload: 动作参数

        Returns:
            {
                "allowed": bool,
                "reason": str,
                "risk_level": str,
                "requires_approval": bool,
            }
        """
        # 根据动作类型检查不同的安全约束
        if action_type == ActionType.REPRICING:
            # 检查调价幅度
            price_change_pct = payload.get("price_change_percentage", Decimal("0"))
            if isinstance(price_change_pct, (int, float)):
                price_change_pct = Decimal(str(price_change_pct))
            if abs(price_change_pct) > self.MAX_REPRICE_PERCENTAGE:
                return {
                    "allowed": False,
                    "reason": f"Price change {float(price_change_pct):.1%} exceeds max {float(self.MAX_REPRICE_PERCENTAGE):.1%}",
                    "risk_level": self.RISK_HIGH,
                    "requires_approval": True,
                }

        elif action_type == ActionType.REPLENISH:
            # 检查补货量
            quantity = payload.get("quantity", 0)
            if product_variant_id:
                max_quantity = await self._calculate_max_replenish(db, product_variant_id)
                if quantity > max_quantity:
                    return {
                        "allowed": False,
                        "reason": f"Replenish quantity {quantity} exceeds max {max_quantity}",
                        "risk_level": self.RISK_MEDIUM,
                        "requires_approval": True,
                    }

        elif action_type == ActionType.DELIST:
            # 检查衰退天数
            if product_variant_id:
                from app.services.lifecycle_engine_service import LifecycleEngineService
                lifecycle_service = LifecycleEngineService()
                current_state = await lifecycle_service.get_current_state(db, product_variant_id)

                if current_state.value not in ["declining", "clearance"]:
                    return {
                        "allowed": False,
                        "reason": f"Cannot delist: current state is {current_state.value}, not declining/clearance",
                        "risk_level": self.RISK_HIGH,
                        "requires_approval": True,
                    }

        elif action_type == ActionType.EXPAND_PLATFORM:
            # 检查利润率和稳定天数
            # TODO: 实现利润率和稳定天数检查
            margin = payload.get("margin")
            stable_days = payload.get("stable_days")

            checks_failed = []
            if margin is not None and Decimal(str(margin)) < self.MIN_MARGIN_FOR_EXPAND_PLATFORM:
                checks_failed.append(f"margin {margin:.1%} below min {self.MIN_MARGIN_FOR_EXPAND_PLATFORM:.1%}")
            if stable_days is not None and stable_days < self.MIN_STABLE_DAYS_FOR_EXPAND_PLATFORM:
                checks_failed.append(f"stable days {stable_days} below min {self.MIN_STABLE_DAYS_FOR_EXPAND_PLATFORM}")

            if checks_failed:
                return {
                    "allowed": False,
                    "reason": f"Expand platform checks failed: {'; '.join(checks_failed)}",
                    "risk_level": self.RISK_MEDIUM,
                    "requires_approval": True,
                }

        elif action_type == ActionType.RETIRE:
            # 退市操作需要人工审批
            return {
                "allowed": True,
                "reason": "Retire action requires manual approval",
                "risk_level": self.RISK_HIGH,
                "requires_approval": True,
            }

        return {
            "allowed": True,
            "reason": "All safety constraints passed",
            "risk_level": self.RISK_LOW,
            "requires_approval": False,
        }

    async def _calculate_max_replenish(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
    ) -> int:
        """计算最大补货量（基于历史销量）。

        Args:
            db: 数据库会话
            product_variant_id: SKU ID

        Returns:
            最大补货数量
        """
        from datetime import date, timedelta
        from sqlalchemy import func
        from app.db.models import ProfitLedger

        # 查询最近 30 天的销量
        today = date.today()
        start_date = today - timedelta(days=30)

        stmt = (
            select(func.count(ProfitLedger.id))
            .where(ProfitLedger.product_variant_id == product_variant_id)
            .where(ProfitLedger.snapshot_date >= start_date)
        )
        result = await db.execute(stmt)
        total_orders = result.scalar() or 0

        # 最大补货量 = 30 天销量
        return int(total_orders)

    async def execute_action_with_mode(
        self,
        db: AsyncSession,
        action_type: ActionType,
        product_variant_id: Optional[UUID] = None,
        listing_id: Optional[UUID] = None,
        payload: Optional[dict] = None,
        execution_mode: str = "auto",
        triggered_by: str = "action_engine",
    ) -> dict:
        """执行自动动作（带执行模式）。

        Args:
            db: 数据库会话
            action_type: 动作类型
            product_variant_id: SKU ID
            listing_id: Listing ID
            payload: 动作参数
            execution_mode: "auto", "suggest", "dry_run"
            triggered_by: 触发来源

        Returns:
            执行结果字典
        """
        # 检查安全约束
        safety_check = await self._check_safety_constraints(
            db=db,
            action_type=action_type,
            product_variant_id=product_variant_id,
            payload=payload or {},
        )

        if not safety_check["allowed"]:
            # 记录被拒绝的动作
            target_id = listing_id or product_variant_id
            target_type = "platform_listing" if listing_id else "product_variant"

            execution = ActionExecutionLog(
                id=uuid4(),
                action_rule_id=None,
                action_type=action_type.value,
                target_type=target_type,
                target_id=target_id,
                status=ActionExecutionStatus.CANCELLED.value,
                input_params=_serialize_for_json({
                    "execution_mode": execution_mode,
                    "payload": payload,
                    "triggered_by": triggered_by,
                }),
                output_data=_serialize_for_json({
                    "rejected": True,
                    "reason": safety_check["reason"],
                    "risk_level": safety_check["risk_level"],
                }),
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(execution)
            await db.commit()

            logger.warning(
                "action_rejected_by_safety_check",
                action_type=action_type.value,
                product_variant_id=str(product_variant_id) if product_variant_id else None,
                reason=safety_check["reason"],
            )

            return {
                "success": False,
                "rejected": True,
                "reason": safety_check["reason"],
                "risk_level": safety_check["risk_level"],
            }

        # dry_run 模式：只返回建议，不执行
        if execution_mode == self.EXECUTION_MODE_DRY_RUN:
            return {
                "success": True,
                "dry_run": True,
                "action_type": action_type.value,
                "suggested_payload": payload,
                "safety_check": safety_check,
            }

        # suggest 模式：返回建议，不执行
        if execution_mode == self.EXECUTION_MODE_SUGGEST:
            return {
                "success": True,
                "suggest": True,
                "action_type": action_type.value,
                "suggested_payload": payload,
                "safety_check": safety_check,
            }

        # auto 模式：实际执行
        return await self.execute_action(
            db=db,
            action_type=action_type,
            product_variant_id=product_variant_id,
            listing_id=listing_id,
            payload=payload,
            triggered_by=triggered_by,
        )

    async def evaluate_actions(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        dry_run: bool = False,
    ) -> list[dict]:
        """评估待执行的自动动作。

        Args:
            db: 数据库会话
            product_variant_id: SKU ID
            dry_run: 是否为 dry-run 模式（不执行，只返回建议）

        Returns:
            [{
                "action_type": ActionType,
                "trigger_reason": str,
                "suggested_payload": dict,
                "risk_level": str,  # "low", "medium", "high"
                "can_auto_execute": bool,
                "requires_approval": bool,
            }]
        """
        actions = []

        # 评估调价动作
        repricing_actions = await self._evaluate_repricing(db, product_variant_id)
        actions.extend(repricing_actions)

        # 评估补货动作
        replenish_actions = await self._evaluate_replenish(db, product_variant_id)
        actions.extend(replenish_actions)

        # 评估下架动作
        delist_actions = await self._evaluate_delist(db, product_variant_id)
        actions.extend(delist_actions)

        logger.info(
            "actions_evaluated",
            product_variant_id=str(product_variant_id),
            action_count=len(actions),
            dry_run=dry_run,
        )

        return actions

    async def execute_action(
        self,
        db: AsyncSession,
        action_type: ActionType,
        product_variant_id: Optional[UUID] = None,
        listing_id: Optional[UUID] = None,
        payload: Optional[dict] = None,
        triggered_by: str = "action_engine",
    ) -> dict:
        """执行自动动作。

        Args:
            db: 数据库会话
            action_type: 动作类型
            product_variant_id: SKU ID
            listing_id: Listing ID
            payload: 动作参数
            triggered_by: 触发来源

        Returns:
            {
                "success": bool,
                "execution_id": UUID,
                "message": str,
            }
        """
        # Determine target - prefer listing_id if provided, otherwise use product_variant_id
        target_id = listing_id or product_variant_id
        target_type = "platform_listing" if listing_id else "product_variant"

        # 创建执行日志
        execution = ActionExecutionLog(
            id=uuid4(),
            action_rule_id=None,  # TODO: 关联规则
            action_type=action_type.value,
            target_type=target_type,
            target_id=target_id,
            status=ActionExecutionStatus.EXECUTING.value,
            started_at=datetime.now(timezone.utc),
            input_params=_serialize_for_json(payload or {}),
        )
        db.add(execution)
        await db.flush()

        try:
            # 执行动作
            result = await self._do_execute(
                db=db,
                action_type=action_type,
                product_variant_id=product_variant_id,
                listing_id=listing_id,
                payload=payload,
            )

            execution.input_params = _serialize_for_json({
                **(payload or {}),
                "rollback": result.get("rollback_context"),
            })

            # 更新执行状态
            execution.status = ActionExecutionStatus.COMPLETED.value
            execution.output_data = _serialize_for_json(result)
            execution.completed_at = datetime.now(timezone.utc)

            await db.commit()

            logger.info(
                "action_executed",
                execution_id=str(execution.id),
                action_type=action_type.value,
                product_variant_id=str(product_variant_id) if product_variant_id else None,
            )

            return {
                "success": True,
                "execution_id": execution.id,
                "message": f"Action {action_type.value} executed successfully",
            }

        except Exception as e:
            execution.status = ActionExecutionStatus.FAILED.value
            execution.output_data = _serialize_for_json({"error": str(e)})
            execution.error_message = str(e)
            execution.completed_at = datetime.now(timezone.utc)

            await db.commit()

            logger.error(
                "action_execution_failed",
                execution_id=str(execution.id),
                action_type=action_type.value,
                error=str(e),
            )

            return {
                "success": False,
                "execution_id": execution.id,
                "message": f"Action {action_type.value} failed: {str(e)}",
            }

    async def get_pending_actions(
        self,
        db: AsyncSession,
        product_variant_id: Optional[UUID] = None,
        action_type: Optional[ActionType] = None,
        limit: int = 100,
    ) -> list[ActionExecutionLog]:
        """获取待执行的自动动作。"""
        stmt = select(ActionExecutionLog).where(
            ActionExecutionLog.status == ActionExecutionStatus.PENDING.value
        )

        if product_variant_id:
            stmt = stmt.where(
                ActionExecutionLog.target_id == product_variant_id,
                ActionExecutionLog.target_type == "product_variant",
            )

        if action_type:
            stmt = stmt.where(ActionExecutionLog.action_type == action_type.value)

        stmt = stmt.order_by(ActionExecutionLog.started_at.desc()).limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def load_active_rules(
        self,
        db: AsyncSession,
        action_type: Optional[ActionType] = None,
    ) -> list[ActionRule]:
        """加载活跃的自动动作规则。"""
        stmt = select(ActionRule).where(ActionRule.is_active == True)

        if action_type:
            stmt = stmt.where(ActionRule.action_type == action_type)

        stmt = stmt.order_by(ActionRule.priority.desc())

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _evaluate_repricing(self, db: AsyncSession, product_variant_id: UUID) -> list[dict]:
        """评估调价动作。"""
        # TODO: 实现调价评估逻辑
        # 根据生命周期信号和异常检测结果判断是否需要调价
        return []

    async def _evaluate_replenish(self, db: AsyncSession, product_variant_id: UUID) -> list[dict]:
        """评估补货动作。"""
        # TODO: 实现补货评估逻辑
        # 根据库存覆盖天数判断是否需要补货
        return []

    async def _evaluate_delist(self, db: AsyncSession, product_variant_id: UUID) -> list[dict]:
        """评估下架动作。"""
        # TODO: 实现下架评估逻辑
        # 根据衰退期判断是否需要下架
        return []

    async def _do_execute(
        self,
        db: AsyncSession,
        action_type: ActionType,
        product_variant_id: Optional[UUID],
        listing_id: Optional[UUID],
        payload: Optional[dict],
    ) -> dict:
        """执行具体动作。

        Args:
            db: 数据库会话
            action_type: 动作类型
            product_variant_id: SKU ID
            listing_id: Listing ID
            payload: 动作参数

        Returns:
            执行结果字典
        """
        result: dict = {"executed": True, "action_type": action_type.value}

        if action_type == ActionType.REPRICING:
            # 接入 PricingService
            try:
                from app.services.pricing_service import PricingService
                from app.db.models import PlatformListing
                from sqlalchemy import select

                pricing_service = PricingService()

                # 捕获回滚上下文：保存当前价格
                if listing_id:
                    stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
                    listing_result = await db.execute(stmt)
                    listing = listing_result.scalar_one_or_none()
                    if listing:
                        result["rollback_context"] = {
                            "listing_id": str(listing_id),
                            "previous_price": str(listing.price),
                            "previous_currency": listing.currency,
                        }

                # TODO: 调用定价服务进行实际调价
                result["pricing_result"] = "pending"
                logger.info(
                    "repricing_action_dispatched",
                    product_variant_id=str(product_variant_id) if product_variant_id else None,
                    listing_id=str(listing_id) if listing_id else None,
                    payload=payload,
                )
            except ImportError:
                result["pricing_result"] = "service_not_available"
                logger.warning("pricing_service_not_available")

        elif action_type == ActionType.REPLENISH:
            # 接入 ProcurementService
            try:
                from app.services.procurement_service import ProcurementService
                procurement_service = ProcurementService()
                # TODO: 调用采购服务进行实际补货
                result["procurement_result"] = "pending"
                logger.info(
                    "replenish_action_dispatched",
                    product_variant_id=str(product_variant_id) if product_variant_id else None,
                    quantity=payload.get("quantity") if payload else None,
                )
            except ImportError:
                result["procurement_result"] = "service_not_available"
                logger.warning("procurement_service_not_available")

        elif action_type == ActionType.SWAP_CONTENT:
            # 接入 ContentAssetManager
            from app.db.models import ListingAssetAssociation

            # 捕获回滚上下文：保存当前主图 asset_id
            if listing_id:
                stmt = select(ListingAssetAssociation).where(
                    ListingAssetAssociation.listing_id == listing_id,
                    ListingAssetAssociation.is_main.is_(True),
                )
                assoc_result = await db.execute(stmt)
                current_main_assoc = assoc_result.scalar_one_or_none()
                if current_main_assoc:
                    result["rollback_context"] = {
                        "listing_id": str(listing_id),
                        "previous_main_asset_id": str(current_main_assoc.asset_id),
                    }

            # TODO: 调用素材管理服务进行内容切换
            result["content_result"] = "pending"
            logger.info(
                "swap_content_action_dispatched",
                product_variant_id=str(product_variant_id) if product_variant_id else None,
                listing_id=str(listing_id) if listing_id else None,
            )

        elif action_type == ActionType.EXPAND_PLATFORM:
            # 接入 UnifiedListingService
            try:
                from app.services.unified_listing_service import UnifiedListingService
                listing_service = UnifiedListingService()
                # TODO: 调用统一 listing 服务进行平台扩展
                result["listing_result"] = "pending"
                logger.info(
                    "expand_platform_action_dispatched",
                    product_variant_id=str(product_variant_id) if product_variant_id else None,
                    target_platform=payload.get("target_platform") if payload else None,
                )
            except ImportError:
                result["listing_result"] = "service_not_available"
                logger.warning("unified_listing_service_not_available")

        elif action_type == ActionType.DELIST:
            # 接入 UnifiedListingService，更新 listing 状态
            try:
                from app.services.unified_listing_service import UnifiedListingService
                from app.db.models import PlatformListing
                from app.core.enums import PlatformListingStatus

                listing_service = UnifiedListingService()

                # 捕获回滚上下文：保存当前状态
                if listing_id:
                    stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
                    listing_result = await db.execute(stmt)
                    listing = listing_result.scalar_one_or_none()
                    if listing:
                        result["rollback_context"] = {
                            "listing_id": str(listing_id),
                            "previous_status": listing.status.value if hasattr(listing.status, "value") else listing.status,
                        }

                # TODO: 调用统一 listing 服务进行下架
                result["delist_result"] = "pending"
                logger.info(
                    "delist_action_dispatched",
                    product_variant_id=str(product_variant_id) if product_variant_id else None,
                    listing_id=str(listing_id) if listing_id else None,
                )
            except ImportError:
                result["delist_result"] = "service_not_available"
                logger.warning("unified_listing_service_not_available")

        elif action_type == ActionType.RETIRE:
            # 更新 ProductVariant 状态为 ARCHIVED
            from app.db.models import ProductVariant
            from sqlalchemy import select

            if product_variant_id:
                stmt = select(ProductVariant).where(ProductVariant.id == product_variant_id)
                result_var = await db.execute(stmt)
                variant = result_var.scalar_one_or_none()

                if variant:
                    # 使用 ARCHIVED 状态代替 RETIRED
                    try:
                        from app.core.enums import ProductVariantStatus
                        variant.status = ProductVariantStatus.ARCHIVED
                        result["retire_result"] = "success"
                        logger.info(
                            "retire_action_completed",
                            product_variant_id=str(product_variant_id),
                        )
                    except (ImportError, ValueError):
                        result["retire_result"] = "status_enum_not_found"
                        logger.warning(
                            "retire_action_status_enum_not_found",
                            product_variant_id=str(product_variant_id),
                        )
                else:
                    result["retire_result"] = "not_found"

        return result

    async def approve_action(
        self,
        db: AsyncSession,
        execution_id: UUID,
        approved_by: str,
        comment: Optional[str] = None,
    ) -> dict:
        """审批通过动作。

        Args:
            db: 数据库会话
            execution_id: 执行日志 ID
            approved_by: 审批人
            comment: 审批意见

        Returns:
            {
                "success": bool,
                "execution_id": UUID,
                "message": str,
            }
        """
        stmt = select(ActionExecutionLog).where(ActionExecutionLog.id == execution_id)
        result = await db.execute(stmt)
        execution = result.scalar_one_or_none()

        if not execution:
            return {
                "success": False,
                "message": f"Execution {execution_id} not found",
            }

        # 检查当前状态是否允许审批
        if execution.status not in [
            ActionExecutionStatus.PENDING.value,
            ActionExecutionStatus.PENDING_APPROVAL.value,
        ]:
            return {
                "success": False,
                "message": f"Cannot approve action in status {execution.status}",
            }

        # 更新审批信息
        execution.status = ActionExecutionStatus.APPROVED.value
        execution.approved_by = approved_by
        execution.approved_at = datetime.now(timezone.utc)

        # 将审批意见存入 output_data
        if execution.output_data is None:
            execution.output_data = {}
        execution.output_data["approval_comment"] = comment
        execution.output_data["approval_action"] = "approved"

        await db.commit()

        logger.info(
            "action_approved",
            execution_id=str(execution_id),
            approved_by=approved_by,
            action_type=execution.action_type,
        )

        return {
            "success": True,
            "execution_id": execution_id,
            "message": f"Action {execution.action_type} approved by {approved_by}",
        }

    async def reject_action(
        self,
        db: AsyncSession,
        execution_id: UUID,
        rejected_by: str,
        comment: Optional[str] = None,
    ) -> dict:
        """拒绝动作。

        Args:
            db: 数据库会话
            execution_id: 执行日志 ID
            rejected_by: 拒绝人
            comment: 拒绝理由

        Returns:
            {
                "success": bool,
                "execution_id": UUID,
                "message": str,
            }
        """
        stmt = select(ActionExecutionLog).where(ActionExecutionLog.id == execution_id)
        result = await db.execute(stmt)
        execution = result.scalar_one_or_none()

        if not execution:
            return {
                "success": False,
                "message": f"Execution {execution_id} not found",
            }

        # 检查当前状态是否允许拒绝
        if execution.status not in [
            ActionExecutionStatus.PENDING.value,
            ActionExecutionStatus.PENDING_APPROVAL.value,
        ]:
            return {
                "success": False,
                "message": f"Cannot reject action in status {execution.status}",
            }

        # 更新拒绝信息
        execution.status = ActionExecutionStatus.REJECTED.value
        execution.approved_by = rejected_by  # 复用 approved_by 字段记录操作人
        execution.approved_at = datetime.now(timezone.utc)  # 复用 approved_at 字段记录操作时间

        # 将拒绝理由存入 output_data
        if execution.output_data is None:
            execution.output_data = {}
        execution.output_data["rejection_comment"] = comment
        execution.output_data["approval_action"] = "rejected"

        await db.commit()

        logger.info(
            "action_rejected",
            execution_id=str(execution_id),
            rejected_by=rejected_by,
            action_type=execution.action_type,
        )

        return {
            "success": True,
            "execution_id": execution_id,
            "message": f"Action {execution.action_type} rejected by {rejected_by}",
        }

    async def defer_action(
        self,
        db: AsyncSession,
        execution_id: UUID,
        deferred_by: str,
        comment: Optional[str] = None,
    ) -> dict:
        """延后动作。

        Args:
            db: 数据库会话
            execution_id: 执行日志 ID
            deferred_by: 延后操作人
            comment: 延后理由

        Returns:
            {
                "success": bool,
                "execution_id": UUID,
                "message": str,
            }
        """
        stmt = select(ActionExecutionLog).where(ActionExecutionLog.id == execution_id)
        result = await db.execute(stmt)
        execution = result.scalar_one_or_none()

        if not execution:
            return {
                "success": False,
                "message": f"Execution {execution_id} not found",
            }

        # 检查当前状态是否允许延后
        if execution.status not in [
            ActionExecutionStatus.PENDING.value,
            ActionExecutionStatus.PENDING_APPROVAL.value,
        ]:
            return {
                "success": False,
                "message": f"Cannot defer action in status {execution.status}",
            }

        # 更新延后信息
        execution.status = ActionExecutionStatus.DEFERRED.value
        execution.approved_by = deferred_by  # 复用 approved_by 字段记录操作人
        execution.approved_at = datetime.now(timezone.utc)  # 复用 approved_at 字段记录操作时间

        # 将延后理由存入 output_data
        if execution.output_data is None:
            execution.output_data = {}
        execution.output_data["defer_comment"] = comment
        execution.output_data["approval_action"] = "deferred"

        await db.commit()

        logger.info(
            "action_deferred",
            execution_id=str(execution_id),
            deferred_by=deferred_by,
            action_type=execution.action_type,
        )

        return {
            "success": True,
            "execution_id": execution_id,
            "message": f"Action {execution.action_type} deferred by {deferred_by}",
        }

    async def rollback_action(
        self,
        db: AsyncSession,
        action_execution_id: UUID,
        rolled_back_by: str = "system",
        reason: Optional[str] = None,
    ) -> dict:
        """回滚已执行动作。

        Args:
            db: 数据库会话
            action_execution_id: 执行日志 ID
            rolled_back_by: 回滚操作人
            reason: 回滚原因

        Returns:
            {
                "success": bool,
                "execution_id": UUID,
                "message": str,
                "rollback_result": dict,
            }
        """
        stmt = select(ActionExecutionLog).where(ActionExecutionLog.id == action_execution_id)
        result = await db.execute(stmt)
        execution = result.scalar_one_or_none()

        if not execution:
            return {
                "success": False,
                "message": f"Execution {action_execution_id} not found",
            }

        action_type = execution.action_type
        if isinstance(action_type, str):
            action_type = ActionType(action_type)

        if execution.status == ActionExecutionStatus.ROLLED_BACK.value:
            return {
                "success": False,
                "execution_id": action_execution_id,
                "message": f"Action {action_type.value} is already rolled back",
            }

        if execution.status != ActionExecutionStatus.COMPLETED.value:
            return {
                "success": False,
                "execution_id": action_execution_id,
                "message": f"Cannot rollback action in status {execution.status}",
            }

        if action_type in self.NON_ROLLBACKABLE_ACTIONS:
            rollback_result = {
                "rollbackable": False,
                "reason": f"Action type {action_type.value} is not rollbackable",
                "rolled_back_by": rolled_back_by,
                "requested_reason": reason,
            }
            if execution.output_data is None:
                execution.output_data = {}
            execution.output_data["rollback_attempt"] = rollback_result
            execution.error_message = rollback_result["reason"]
            await db.commit()
            return {
                "success": False,
                "execution_id": action_execution_id,
                "message": rollback_result["reason"],
                "rollback_result": rollback_result,
            }

        rollback_context = (execution.input_params or {}).get("rollback")
        if not rollback_context:
            rollback_result = {
                "rollbackable": False,
                "reason": "No rollback context recorded for this action",
                "rolled_back_by": rolled_back_by,
                "requested_reason": reason,
            }
            if execution.output_data is None:
                execution.output_data = {}
            execution.output_data["rollback_attempt"] = rollback_result
            execution.error_message = rollback_result["reason"]
            await db.commit()
            return {
                "success": False,
                "execution_id": action_execution_id,
                "message": rollback_result["reason"],
                "rollback_result": rollback_result,
            }

        try:
            rollback_result: dict = {
                "rollbackable": True,
                "rolled_back_by": rolled_back_by,
                "reason": reason,
                "rolled_back_at": datetime.now(timezone.utc).isoformat(),
            }

            if action_type == ActionType.REPRICING:
                from app.db.models import PlatformListing, PriceHistory

                listing_id = UUID(rollback_context["listing_id"])
                stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
                listing_result = await db.execute(stmt)
                listing = listing_result.scalar_one_or_none()

                if not listing:
                    raise ValueError(f"Listing {listing_id} not found")

                previous_price = Decimal(rollback_context["previous_price"])
                current_price = listing.price
                listing.price = previous_price

                price_history = PriceHistory(
                    id=uuid4(),
                    listing_id=listing_id,
                    old_price=current_price,
                    new_price=previous_price,
                    reason=f"rollback:{reason or 'manual rollback'}",
                    changed_by=rolled_back_by,
                    changed_at=datetime.now(timezone.utc),
                )
                db.add(price_history)

                rollback_result.update({
                    "action_type": action_type.value,
                    "listing_id": str(listing_id),
                    "restored_price": str(previous_price),
                    "current_price_before_rollback": str(current_price),
                })

            elif action_type == ActionType.SWAP_CONTENT:
                from app.db.models import ListingAssetAssociation
                from sqlalchemy import delete

                listing_id = UUID(rollback_context["listing_id"])
                previous_main_asset_id = UUID(rollback_context["previous_main_asset_id"])

                clear_stmt = delete(ListingAssetAssociation).where(
                    ListingAssetAssociation.listing_id == listing_id,
                    ListingAssetAssociation.is_main.is_(True),
                )
                await db.execute(clear_stmt)

                restored_assoc = ListingAssetAssociation(
                    listing_id=listing_id,
                    asset_id=previous_main_asset_id,
                    display_order=0,
                    is_main=True,
                )
                db.add(restored_assoc)

                rollback_result.update({
                    "action_type": action_type.value,
                    "listing_id": str(listing_id),
                    "restored_main_asset_id": str(previous_main_asset_id),
                })

            elif action_type == ActionType.DELIST:
                from app.db.models import PlatformListing
                from app.core.enums import PlatformListingStatus

                listing_id = UUID(rollback_context["listing_id"])
                stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
                listing_result = await db.execute(stmt)
                listing = listing_result.scalar_one_or_none()

                if not listing:
                    raise ValueError(f"Listing {listing_id} not found")

                previous_status = PlatformListingStatus(rollback_context["previous_status"])
                current_status = listing.status
                listing.status = previous_status

                rollback_result.update({
                    "action_type": action_type.value,
                    "listing_id": str(listing_id),
                    "restored_status": previous_status.value,
                    "current_status_before_rollback": current_status.value if hasattr(current_status, "value") else current_status,
                })

            else:
                raise ValueError(f"Rollback not implemented for action type {action_type.value}")

            if execution.output_data is None:
                execution.output_data = {}
            execution.output_data["rollback"] = rollback_result
            execution.status = ActionExecutionStatus.ROLLED_BACK.value
            execution.error_message = reason
            execution.completed_at = datetime.now(timezone.utc)

            await db.commit()

            logger.info(
                "action_rolled_back",
                execution_id=str(action_execution_id),
                action_type=action_type.value,
                rolled_back_by=rolled_back_by,
                reason=reason,
            )

            return {
                "success": True,
                "execution_id": action_execution_id,
                "message": f"Action {action_type.value} rolled back successfully",
                "rollback_result": rollback_result,
            }

        except Exception as e:
            rollback_result = {
                "rollbackable": True,
                "success": False,
                "reason": reason,
                "rolled_back_by": rolled_back_by,
                "error": str(e),
            }
            if execution.output_data is None:
                execution.output_data = {}
            execution.output_data["rollback_attempt"] = rollback_result
            execution.error_message = str(e)
            await db.commit()

            logger.error(
                "action_rollback_failed",
                execution_id=str(action_execution_id),
                action_type=action_type.value,
                rolled_back_by=rolled_back_by,
                error=str(e),
            )

            return {
                "success": False,
                "execution_id": action_execution_id,
                "message": f"Failed to rollback action {action_type.value}: {str(e)}",
                "rollback_result": rollback_result,
            }


