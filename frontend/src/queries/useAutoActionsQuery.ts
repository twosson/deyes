import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import type { MaybeRef } from 'vue'
import { computed, unref } from 'vue'

import { approveListing, getPendingApprovals, rejectListing } from '@/api/autoActions'
import { getErrorMessage } from '@/api/http'
import type { UUID } from '@/types/common'
import type { ApprovalRequest } from '@/types/autoActions'

/**
 * 获取待审批列表
 */
export function usePendingApprovalsQuery(params?: MaybeRef<{ platform?: string; limit?: number }>) {
  return useQuery({
    queryKey: computed(() => ['auto-actions', 'pending-approval', unref(params)]),
    queryFn: () => getPendingApprovals(unref(params)),
    refetchInterval: 30000, // 每30秒自动刷新
  })
}

/**
 * 审批通过 mutation
 */
export function useApproveListingMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ listingId, payload }: { listingId: UUID; payload: ApprovalRequest }) =>
      approveListing(listingId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['auto-actions', 'pending-approval'] })
      void queryClient.invalidateQueries({ queryKey: ['platform-listings'] })
      message.success('审批通过，商品已发布')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

/**
 * 审批拒绝 mutation
 */
export function useRejectListingMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ listingId, payload }: { listingId: UUID; payload: ApprovalRequest }) =>
      rejectListing(listingId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['auto-actions', 'pending-approval'] })
      void queryClient.invalidateQueries({ queryKey: ['platform-listings'] })
      message.success('审批已拒绝')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}
