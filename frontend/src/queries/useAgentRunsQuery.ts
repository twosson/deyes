import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import type { MaybeRef } from 'vue'
import { computed, unref } from 'vue'

import {
  createAgentRun,
  getAgentRunResults,
  getAgentRunStatus,
  getAgentRunSteps,
  listAgentRuns,
} from '@/api/agentRuns'
import { getErrorMessage } from '@/api/http'
import type { CreateAgentRunRequest } from '@/types/agentRuns'
import type { UUID } from '@/types/common'

export function useCreateAgentRunMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateAgentRunRequest) => createAgentRun(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['candidates'] })
      void queryClient.invalidateQueries({ queryKey: ['agent-runs', 'list'] })
      message.success('选品任务已创建')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

export function useAgentRunsListQuery(params?: MaybeRef<Record<string, unknown>>) {
  return useQuery({
    queryKey: computed(() => ['agent-runs', 'list', unref(params)]),
    queryFn: () => listAgentRuns(unref(params)),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => {
      const runs = query.state.data?.runs ?? []
      return runs.some((run) => run.status === 'queued' || run.status === 'running') ? 5000 : false
    },
  })
}

export function useAgentRunStatusQuery(runId: MaybeRef<UUID | null | undefined>) {
  const enabled = computed(() => !!unref(runId))

  return useQuery({
    queryKey: computed(() => ['agent-runs', unref(runId), 'status']),
    queryFn: () => getAgentRunStatus(unref(runId) as UUID),
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status || status === 'queued' || status === 'running') {
        return 5000
      }
      return false
    },
  })
}

export function useAgentRunStepsQuery(runId: MaybeRef<UUID | null | undefined>) {
  const enabled = computed(() => !!unref(runId))

  return useQuery({
    queryKey: computed(() => ['agent-runs', unref(runId), 'steps']),
    queryFn: () => getAgentRunSteps(unref(runId) as UUID),
    enabled,
    refetchInterval: (query) => {
      const steps = query.state.data?.steps ?? []
      if (steps.length === 0) {
        return 5000
      }
      return steps.some((step) => step.status === 'pending' || step.status === 'running') ? 5000 : false
    },
  })
}

export function useAgentRunResultsQuery(runId: MaybeRef<UUID | null | undefined>) {
  const enabled = computed(() => !!unref(runId))

  return useQuery({
    queryKey: computed(() => ['agent-runs', unref(runId), 'results']),
    queryFn: () => getAgentRunResults(unref(runId) as UUID),
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status || status === 'queued' || status === 'running') {
        return 5000
      }
      return false
    },
  })
}
