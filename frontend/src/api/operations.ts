import type { UUID } from '@/types/common'
import type {
  ActionExecutionResponse,
  ApprovalRequest,
  ClearanceCandidate,
  DeferRequest,
  ExceptionsResponse,
  LifecycleStateResponse,
  OperationResponse,
  OperationsSummaryResponse,
  PendingAction,
  RejectionRequest,
  RollbackRequest,
  ScalingCandidate,
} from '@/types/operations'

import { get, post } from './http'

export interface OperationsListParams {
  platform?: string
  region?: string
  limit?: number
}

/**
 * 获取今日异常列表。
 */
export async function getExceptions(params?: OperationsListParams): Promise<ExceptionsResponse> {
  return get<ExceptionsResponse>('/operations/exceptions', { params })
}

/**
 * 获取值得加码的 SKU 列表。
 */
export async function getScalingCandidates(
  params?: OperationsListParams
): Promise<ScalingCandidate[]> {
  return get<ScalingCandidate[]>('/operations/scaling-candidates', { params })
}

/**
 * 获取应清退的 SKU 列表。
 */
export async function getClearanceCandidates(
  params?: OperationsListParams
): Promise<ClearanceCandidate[]> {
  return get<ClearanceCandidate[]>('/operations/clearance-candidates', { params })
}

/**
 * 获取待审批动作列表。
 */
export async function getPendingActions(params?: OperationsListParams): Promise<PendingAction[]> {
  return get<PendingAction[]>('/operations/pending-actions', { params })
}

/**
 * 获取 SKU 生命周期状态。
 */
export async function getLifecycleState(variantId: UUID): Promise<LifecycleStateResponse> {
  return get<LifecycleStateResponse>(`/operations/lifecycle/${variantId}`)
}

/**
 * 获取动作执行详情。
 */
export async function getActionExecution(executionId: UUID): Promise<ActionExecutionResponse> {
  return get<ActionExecutionResponse>(`/operations/actions/${executionId}`)
}

/**
 * 审批通过动作。
 */
export async function approveAction(
  executionId: UUID,
  payload: ApprovalRequest
): Promise<OperationResponse> {
  return post<OperationResponse>(`/operations/actions/${executionId}/approve`, payload)
}

/**
 * 拒绝动作。
 */
export async function rejectAction(
  executionId: UUID,
  payload: RejectionRequest
): Promise<OperationResponse> {
  return post<OperationResponse>(`/operations/actions/${executionId}/reject`, payload)
}

/**
 * 延后动作。
 */
export async function deferAction(
  executionId: UUID,
  payload: DeferRequest
): Promise<OperationResponse> {
  return post<OperationResponse>(`/operations/actions/${executionId}/defer`, payload)
}

/**
 * 回滚已执行动作。
 */
export async function rollbackAction(
  executionId: UUID,
  payload: RollbackRequest
): Promise<OperationResponse> {
  return post<OperationResponse>(`/operations/actions/${executionId}/rollback`, payload)
}

/**
 * 获取运营控制台汇总视图。
 */
export async function getOperationsSummary(): Promise<OperationsSummaryResponse> {
  return get<OperationsSummaryResponse>('/operations/summary')
}
