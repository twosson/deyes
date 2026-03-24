import type { AgentRunResponse, AgentRunResultsResponse, AgentRunStatusResponse, CreateAgentRunRequest } from '@/types/agentRuns'
import type { UUID } from '@/types/common'
import type { AgentRunStepsResponse, ListStrategyRunsResponse } from '@/types/taskMonitor'

import { get, post } from './http'

export async function createAgentRun(payload: CreateAgentRunRequest): Promise<AgentRunResponse> {
  return post<AgentRunResponse>('/agent-runs', payload)
}

export async function listAgentRuns(params?: { status?: string; source_platform?: string; limit?: number; offset?: number }): Promise<ListStrategyRunsResponse> {
  return get<ListStrategyRunsResponse>('/agent-runs', { params })
}

export async function getAgentRunStatus(runId: UUID): Promise<AgentRunStatusResponse> {
  return get<AgentRunStatusResponse>(`/agent-runs/${runId}`)
}

export async function getAgentRunSteps(runId: UUID): Promise<AgentRunStepsResponse> {
  return get<AgentRunStepsResponse>(`/agent-runs/${runId}/steps`)
}

export async function getAgentRunResults(runId: UUID): Promise<AgentRunResultsResponse> {
  return get<AgentRunResultsResponse>(`/agent-runs/${runId}/results`)
}
