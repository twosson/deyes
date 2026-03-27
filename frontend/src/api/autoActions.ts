import type { UUID } from '@/types/common'
import type { ApprovalRequest, PendingApprovalResponse } from '@/types/autoActions'

import { get, post } from './http'

/**
 * 获取待审批列表
 */
export async function getPendingApprovals(params?: {
  platform?: string
  limit?: number
}): Promise<PendingApprovalResponse> {
  return get<PendingApprovalResponse>('/auto-actions/pending-approval', { params })
}

/**
 * 审批通过
 */
export async function approveListing(listingId: UUID, payload: ApprovalRequest) {
  return post(`/auto-actions/approve/${listingId}`, payload)
}

/**
 * 审批拒绝
 */
export async function rejectListing(listingId: UUID, payload: ApprovalRequest) {
  return post(`/auto-actions/reject/${listingId}`, payload)
}
