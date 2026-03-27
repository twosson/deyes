import type { UUID } from './common'

/**
 * 待审批 Listing
 */
export interface PendingApprovalListing {
  id: UUID
  candidate_product_id: UUID
  platform: string
  region: string
  price: number
  currency: string
  status: string
  approval_required: boolean
  approval_reason: string | null
  platform_listing_id: string | null
  platform_url: string | null
  auto_action_metadata: AutoActionMetadata | null
  created_at: string
}

/**
 * 自动操作元数据（服务端重算的真实值）
 */
export interface AutoActionMetadata {
  recommendation_score?: number
  risk_score?: number
  margin_percentage?: number
  created_by?: string
  [key: string]: any
}

/**
 * 待审批列表响应
 */
export interface PendingApprovalResponse {
  items: PendingApprovalListing[]
  count: number
}

/**
 * 审批请求
 */
export interface ApprovalRequest {
  approved_by: string
  reason?: string
}

/**
 * 审批操作类型
 */
export type ApprovalAction = 'approve' | 'reject'
