import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import type { MaybeRef } from 'vue'
import { computed, unref } from 'vue'

import type { ListExperimentsParams } from '@/api/experiments'
import {
  activateExperiment,
  createExperiment,
  getExperiment,
  getExperimentSummary,
  listExperiments,
  promoteWinner,
  selectWinner,
  setWinner,
} from '@/api/experiments'
import { getErrorMessage } from '@/api/http'
import type { UUID } from '@/types/common'
import type { CreateExperimentRequest, ExperimentStatus } from '@/types/experiments'

export function useExperimentsQuery(params?: MaybeRef<ListExperimentsParams>) {
  return useQuery({
    queryKey: computed(() => ['experiments', unref(params)]),
    queryFn: () => listExperiments(unref(params)),
    placeholderData: keepPreviousData,
  })
}

export function useExperimentDetailQuery(experimentId: MaybeRef<UUID | null | undefined>) {
  return useQuery({
    queryKey: computed(() => ['experiments', 'detail', unref(experimentId)]),
    queryFn: () => getExperiment(unref(experimentId) as UUID),
    enabled: computed(() => !!unref(experimentId)),
  })
}

export function useExperimentSummaryQuery(experimentId: MaybeRef<UUID | null | undefined>) {
  return useQuery({
    queryKey: computed(() => ['experiments', 'summary', unref(experimentId)]),
    queryFn: () => getExperimentSummary(unref(experimentId) as UUID),
    enabled: computed(() => !!unref(experimentId)),
    refetchInterval: (data) => {
      // Poll every 30s if experiment is active
      return data?.experiment_status === ('active' as ExperimentStatus) ? 30000 : false
    },
  })
}

export function useCreateExperimentMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateExperimentRequest) => createExperiment(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['experiments'] })
      message.success('实验创建成功')
    },
    onError: (error) => {
      message.error(`创建失败: ${getErrorMessage(error)}`)
    },
  })
}

export function useActivateExperimentMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (experimentId: UUID) => activateExperiment(experimentId),
    onSuccess: (_, experimentId) => {
      void queryClient.invalidateQueries({ queryKey: ['experiments', 'detail', experimentId] })
      void queryClient.invalidateQueries({ queryKey: ['experiments'] })
      message.success('实验已激活')
    },
    onError: (error) => {
      message.error(`激活失败: ${getErrorMessage(error)}`)
    },
  })
}

export function useSelectWinnerMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (experimentId: UUID) => selectWinner(experimentId),
    onSuccess: (_, experimentId) => {
      void queryClient.invalidateQueries({ queryKey: ['experiments', 'detail', experimentId] })
      void queryClient.invalidateQueries({ queryKey: ['experiments', 'summary', experimentId] })
      void queryClient.invalidateQueries({ queryKey: ['experiments'] })
      message.success('获胜者已自动选择')
    },
    onError: (error) => {
      message.error(`选择失败: ${getErrorMessage(error)}`)
    },
  })
}

export function useSetWinnerMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ experimentId, variantGroup }: { experimentId: UUID; variantGroup: string }) =>
      setWinner(experimentId, variantGroup),
    onSuccess: (_, { experimentId }) => {
      void queryClient.invalidateQueries({ queryKey: ['experiments', 'detail', experimentId] })
      void queryClient.invalidateQueries({ queryKey: ['experiments', 'summary', experimentId] })
      void queryClient.invalidateQueries({ queryKey: ['experiments'] })
      message.success('获胜者已设置')
    },
    onError: (error) => {
      message.error(`设置失败: ${getErrorMessage(error)}`)
    },
  })
}

export function usePromoteWinnerMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (experimentId: UUID) => promoteWinner(experimentId),
    onSuccess: (_, experimentId) => {
      void queryClient.invalidateQueries({ queryKey: ['experiments', 'detail', experimentId] })
      void queryClient.invalidateQueries({ queryKey: ['content-assets'] })
      message.success('获胜变体已提升为主图')
    },
    onError: (error) => {
      message.error(`提升失败: ${getErrorMessage(error)}`)
    },
  })
}
