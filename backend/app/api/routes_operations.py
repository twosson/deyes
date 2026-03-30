"""经营控制台 API 路由。

提供只读 API，支持 UI、调试和运营使用。
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Body
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import ActionExecutionLog
from app.services.operations_control_plane_service import OperationsControlPlaneService
from app.services.action_engine_service import ActionEngineService

router = APIRouter(prefix="/operations", tags=["operations"])


class ApprovalRequest(BaseModel):
    """审批请求模型。"""
    approved_by: str
    comment: Optional[str] = None


class RejectionRequest(BaseModel):
    """拒绝请求模型。"""
    rejected_by: str
    comment: Optional[str] = None


class DeferRequest(BaseModel):
    """延后请求模型。"""
    deferred_by: str
    comment: Optional[str] = None


class RollbackRequest(BaseModel):
    """回滚请求模型。"""
    rolled_back_by: str = "manual"
    reason: Optional[str] = None


@router.get("/exceptions")
async def get_exceptions(
    platform: Optional[str] = Query(None, description="Platform filter"),
    region: Optional[str] = Query(None, description="Region filter"),
    limit: int = Query(100, ge=1, le=500, description="Result limit"),
    db: AsyncSession = Depends(get_db),
):
    """今日异常列表。

    Returns:
        {
            "date": str,
            "total_anomalies": int,
            "by_severity": {...},
            "anomalies": [...],
        }
    """
    service = OperationsControlPlaneService()
    return await service.get_daily_exceptions(
        db=db,
        platform=platform,
        region=region,
        limit=limit,
    )


@router.get("/scaling-candidates")
async def get_scaling_candidates(
    platform: Optional[str] = Query(None, description="Platform filter"),
    region: Optional[str] = Query(None, description="Region filter"),
    limit: int = Query(50, ge=1, le=200, description="Result limit"),
    db: AsyncSession = Depends(get_db),
):
    """值得加码的 SKU 列表。

    Returns:
        [
            {
                "product_variant_id": str,
                "current_state": str,
                "confidence_score": float,
                "reason": str,
            },
            ...
        ]
    """
    service = OperationsControlPlaneService()
    return await service.get_scaling_candidates(
        db=db,
        platform=platform,
        region=region,
        limit=limit,
    )


@router.get("/clearance-candidates")
async def get_clearance_candidates(
    platform: Optional[str] = Query(None, description="Platform filter"),
    region: Optional[str] = Query(None, description="Region filter"),
    limit: int = Query(50, ge=1, le=200, description="Result limit"),
    db: AsyncSession = Depends(get_db),
):
    """应清退的 SKU 列表。

    Returns:
        [
            {
                "product_variant_id": str,
                "current_state": str,
                "confidence_score": float,
                "reason": str,
            },
            ...
        ]
    """
    service = OperationsControlPlaneService()
    return await service.get_clearance_candidates(
        db=db,
        platform=platform,
        region=region,
        limit=limit,
    )


@router.get("/pending-actions")
async def get_pending_actions(
    platform: Optional[str] = Query(None, description="Platform filter"),
    region: Optional[str] = Query(None, description="Region filter"),
    limit: int = Query(50, ge=1, le=200, description="Result limit"),
    db: AsyncSession = Depends(get_db),
):
    """待审批动作列表。

    Returns:
        [
            {
                "execution_id": str,
                "action_type": str,
                "product_variant_id": str,
                "listing_id": str,
                "input_params": dict,
                "status": str,
                "created_at": str,
            },
            ...
        ]
    """
    service = OperationsControlPlaneService()
    return await service.get_pending_action_approvals(
        db=db,
        platform=platform,
        region=region,
        limit=limit,
    )


@router.get("/lifecycle/{variant_id}")
async def get_lifecycle_state(
    variant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """SKU 生命周期状态。

    Returns:
        {
            "product_variant_id": str,
            "current_state": str,
            "entered_at": str,
            "confidence_score": float,
        }
    """
    from app.services.lifecycle_engine_service import LifecycleEngineService

    service = LifecycleEngineService()
    current_state = await service.get_current_state(db, variant_id)

    # 获取完整状态记录
    from app.db.models import SkuLifecycleStateModel
    stmt = select(SkuLifecycleStateModel).where(
        SkuLifecycleStateModel.product_variant_id == variant_id
    )
    result = await db.execute(stmt)
    state_record = result.scalar_one_or_none()

    metadata = state_record.state_metadata if state_record else {}
    confidence_score = metadata.get("confidence_score", 0.0)

    return {
        "product_variant_id": str(variant_id),
        "current_state": current_state.value,
        "entered_at": state_record.entered_at.isoformat() if state_record and state_record.entered_at else None,
        "confidence_score": float(confidence_score),
    }


@router.get("/actions/{execution_id}")
async def get_action_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """动作执行详情。

    Returns:
        {
            "execution_id": str,
            "action_type": str,
            "status": str,
            "input_params": dict,
            "output_data": dict,
            "executed_at": str,
        }
    """
    stmt = select(ActionExecutionLog).where(ActionExecutionLog.id == execution_id)
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()

    if not execution:
        return {"error": "Execution not found"}

    return {
        "execution_id": str(execution.id),
        "action_type": execution.action_type.value if hasattr(execution.action_type, 'value') else execution.action_type,
        "status": execution.status.value if hasattr(execution.status, 'value') else execution.status,
        "target_type": execution.target_type,
        "target_id": str(execution.target_id),
        "input_params": execution.input_params,
        "output_data": execution.output_data,
        "error_message": execution.error_message,
        "approved_by": execution.approved_by,
        "approved_at": execution.approved_at.isoformat() if execution.approved_at else None,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
    }


@router.post("/actions/{execution_id}/approve")
async def approve_action(
    execution_id: UUID,
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    """审批通过动作。

    Args:
        execution_id: 执行日志 ID
        request: 审批请求（包含审批人和审批意见）

    Returns:
        {
            "success": bool,
            "execution_id": str,
            "message": str,
        }
    """
    service = ActionEngineService()
    result = await service.approve_action(
        db=db,
        execution_id=execution_id,
        approved_by=request.approved_by,
        comment=request.comment,
    )
    return result


@router.post("/actions/{execution_id}/reject")
async def reject_action(
    execution_id: UUID,
    request: RejectionRequest,
    db: AsyncSession = Depends(get_db),
):
    """拒绝动作。

    Args:
        execution_id: 执行日志 ID
        request: 拒绝请求（包含拒绝人和拒绝理由）

    Returns:
        {
            "success": bool,
            "execution_id": str,
            "message": str,
        }
    """
    service = ActionEngineService()
    result = await service.reject_action(
        db=db,
        execution_id=execution_id,
        rejected_by=request.rejected_by,
        comment=request.comment,
    )
    return result


@router.post("/actions/{execution_id}/defer")
async def defer_action(
    execution_id: UUID,
    request: DeferRequest,
    db: AsyncSession = Depends(get_db),
):
    """延后动作。

    Args:
        execution_id: 执行日志 ID
        request: 延后请求（包含延后操作人和延后理由）

    Returns:
        {
            "success": bool,
            "execution_id": str,
            "message": str,
        }
    """
    service = ActionEngineService()
    result = await service.defer_action(
        db=db,
        execution_id=execution_id,
        deferred_by=request.deferred_by,
        comment=request.comment,
    )
    return result


@router.post("/actions/{execution_id}/rollback")
async def rollback_action(
    execution_id: UUID,
    request: RollbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """回滚已执行动作。

    Args:
        execution_id: 执行日志 ID
        request: 回滚请求（包含回滚操作人和回滚原因）

    Returns:
        {
            "success": bool,
            "execution_id": str,
            "message": str,
            "rollback_result": dict,
        }
    """
    service = ActionEngineService()
    result = await service.rollback_action(
        db=db,
        action_execution_id=execution_id,
        rolled_back_by=request.rolled_back_by,
        reason=request.reason,
    )
    return result


@router.get("/summary")
async def get_operations_summary(
    db: AsyncSession = Depends(get_db),
):
    """运营控制台汇总视图。

    Returns:
        {
            "daily_exceptions": {...},
            "scaling_candidates_count": int,
            "clearance_candidates_count": int,
            "pending_actions_count": int,
        }
    """
    service = OperationsControlPlaneService()
    return await service.get_operations_summary(db=db)
