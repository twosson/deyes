import type { UUID } from './common'

/**
 * 异常严重程度
 */
export type AnomalySeverity = 'critical' | 'high' | 'medium' | 'low'

/**
 * SKU 生命周期状态（与后端 SkuLifecycleState 枚举对齐）
 */
export type SkuLifecycleState =
  | 'discovering'
  | 'testing'
  | 'scaling'
  | 'stable'
  | 'declining'
  | 'clearance'
  | 'retired'

/**
 * 动作类型（与后端 ActionType 枚举对齐）
 */
export type ActionType =
  | 'repricing'
  | 'replenish'
  | 'swap_content'
  | 'expand_platform'
  | 'delist'
  | 'retire'

/**
 * 动作执行状态（与后端 ActionExecutionStatus 枚举对齐）
 */
export type ActionExecutionStatus =
  | 'pending'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'deferred'
  | 'executing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'rolled_back'

/**
 * 异常类型（与后端 anomaly detection 输出对齐）
 */
export type AnomalyType =
  | 'sales_drop'
  | 'refund_spike'
  | 'margin_collapse'
  | 'stockout_risk'
  | 'ctr_drop'
  | 'cvr_drop'
  | 'supplier_delay'
  | 'supplier_fulfillment_issues'

/**
 * 异常记录（与后端 detect_global_anomalies 输出对齐）
 */
export interface Anomaly {
  type: AnomalyType | string
  severity: AnomalySeverity
  product_variant_id?: UUID
  details: Record<string, any>
}

/**
 * 今日异常列表响应
 */
export interface ExceptionsResponse {
  date: string
  total_anomalies: number
  by_severity: Partial<Record<AnomalySeverity, number>>
  anomalies: Anomaly[]
}

/**
 * 扩量候选 SKU
 */
export interface ScalingCandidate {
  product_variant_id: UUID
  current_state: SkuLifecycleState
  entered_at: string | null
  confidence_score: number
  reason: string
}

/**
 * 清退候选 SKU
 */
export interface ClearanceCandidate {
  product_variant_id: UUID
  current_state: SkuLifecycleState
  entered_at: string | null
  confidence_score: number
  reason: string
}

/**
 * 待审批动作
 */
export interface PendingAction {
  execution_id: UUID
  action_type: ActionType
  product_variant_id: UUID | null
  listing_id: UUID | null
  target_type: string
  input_params: Record<string, any>
  status: ActionExecutionStatus
  created_at: string | null
}

/**
 * SKU 生命周期状态响应
 */
export interface LifecycleStateResponse {
  product_variant_id: UUID
  current_state: SkuLifecycleState
  entered_at: string | null
  confidence_score: number
}

/**
 * 动作执行详情响应
 */
export interface ActionExecutionResponse {
  execution_id: UUID
  action_type: ActionType
  status: ActionExecutionStatus
  target_type: string
  target_id: UUID
  input_params: Record<string, any>
  output_data: Record<string, any> | null
  error_message: string | null
  approved_by: string | null
  approved_at: string | null
  started_at: string | null
  completed_at: string | null
}

/**
 * 运营控制台汇总响应
 */
export interface OperationsSummaryResponse {
  daily_exceptions: {
    total: number
    by_severity: Partial<Record<AnomalySeverity, number>>
  }
  scaling_candidates_count: number
  clearance_candidates_count: number
  pending_actions_count: number
}

/**
 * 审批请求
 */
export interface ApprovalRequest {
  approved_by: string
  comment?: string
}

/**
 * 拒绝请求
 */
export interface RejectionRequest {
  rejected_by: string
  comment?: string
}

/**
 * 延后请求
 */
export interface DeferRequest {
  deferred_by: string
  comment?: string
}

/**
 * 回滚请求
 */
export interface RollbackRequest {
  rolled_back_by?: string
  reason?: string
}

/**
 * 操作响应
 */
export interface OperationResponse {
  success: boolean
  execution_id: UUID
  message: string
  rollback_result?: Record<string, any>
}
