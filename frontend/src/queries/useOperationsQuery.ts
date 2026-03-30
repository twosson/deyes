import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import type { MaybeRef } from 'vue'
import { computed, unref } from 'vue'

import {
  approveAction,
  deferAction,
  getActionExecution,
  getClearanceCandidates,
  getExceptions,
  getLifecycleState,
  getOperationsSummary,
  getPendingActions,
  getScalingCandidates,
  rejectAction,
  rollbackAction,
  type OperationsListParams,
} from '@/api/operations'
import { getErrorMessage } from '@/api/http'
import type { UUID } from '@/types/common'
import type { ApprovalRequest, DeferRequest, RejectionRequest, RollbackRequest } from '@/types/operations'

/**
 * 获取今日异常列表。
 */
export function useExceptionsQuery(params?: MaybeRef<OperationsListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => ['operations', 'exceptions', unref(params)]),
    queryFn: () => getExceptions(unref(params)),
    refetchInterval: 30000,
  })
}

/**
 * 获取值得加码的 SKU 列表。
 */
export function useScalingCandidatesQuery(params?: MaybeRef<OperationsListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => ['operations', 'scaling-candidates', unref(params)]),
    queryFn: () => getScalingCandidates(unref(params)),
    refetchInterval: 30000,
  })
}

/**
 * 获取应清退的 SKU 列表。
 */
export function useClearanceCandidatesQuery(params?: MaybeRef<OperationsListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => ['operations', 'clearance-candidates', unref(params)]),
    queryFn: () => getClearanceCandidates(unref(params)),
    refetchInterval: 30000,
  })
}

/**
 * 获取待审批动作列表。
 */
export function usePendingActionsQuery(params?: MaybeRef<OperationsListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => ['operations', 'pending-actions', unref(params)]),
    queryFn: () => getPendingActions(unref(params)),
    refetchInterval: 30000,
  })
}

/**
 * 获取 SKU 生命周期状态。
 */
export function useLifecycleStateQuery(variantId: MaybeRef<UUID | null | undefined>) {
  return useQuery({
    queryKey: computed(() => ['operations', 'lifecycle', unref(variantId)]),
    queryFn: () => getLifecycleState(unref(variantId) as UUID),
    enabled: computed(() => !!unref(variantId)),
  })
}

/**
 * 获取动作执行详情。
 */
export function useActionExecutionQuery(executionId: MaybeRef<UUID | null | undefined>) {
  return useQuery({
    queryKey: computed(() => ['operations', 'actions', unref(executionId)]),
    queryFn: () => getActionExecution(unref(executionId) as UUID),
    enabled: computed(() => !!unref(executionId)),
  })
}

/**
 * 获取运营控制台汇总视图。
 */
export function useOperationsSummaryQuery() {
  return useQuery({
    queryKey: ['operations', 'summary'],
    queryFn: getOperationsSummary,
    refetchInterval: 30000,
  })
}

/**
 * 审批通过动作 mutation。
 */
export function useApproveActionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ executionId, payload }: { executionId: UUID; payload: ApprovalRequest }) =>
      approveAction(executionId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['operations'] })
      message.success('动作已审批通过')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

/**
 * 拒绝动作 mutation。
 */
export function useRejectActionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ executionId, payload }: { executionId: UUID; payload: RejectionRequest }) =>
      rejectAction(executionId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['operations'] })
      message.success('动作已拒绝')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

/**
 * 延后动作 mutation。
 */
export function useDeferActionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ executionId, payload }: { executionId: UUID; payload: DeferRequest }) =>
      deferAction(executionId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['operations'] })
      message.success('动作已延后')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

/**
 * 回滚动作 mutation。
 */
export function useRollbackActionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ executionId, payload }: { executionId: UUID; payload: RollbackRequest }) =>
      rollbackAction(executionId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['operations'] })
      message.success('动作已回滚')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}
