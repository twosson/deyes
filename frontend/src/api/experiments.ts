import type { UUID } from '@/types/common'
import type {
  CreateExperimentRequest,
  Experiment,
  ExperimentSummary,
  ListExperimentsResponse,
} from '@/types/experiments'

import { get, post } from './http'

export interface ListExperimentsParams {
  status?: string
  limit?: number
  offset?: number
}

export async function listExperiments(
  params?: ListExperimentsParams
): Promise<ListExperimentsResponse> {
  return get<ListExperimentsResponse>('/experiments', { params })
}

export async function getExperiment(experimentId: UUID): Promise<Experiment> {
  return get<Experiment>(`/experiments/${experimentId}`)
}

export async function getExperimentSummary(experimentId: UUID): Promise<ExperimentSummary> {
  return get<ExperimentSummary>(`/experiments/${experimentId}/summary`)
}

export async function createExperiment(payload: CreateExperimentRequest): Promise<Experiment> {
  return post<Experiment>('/experiments', payload)
}

export async function activateExperiment(experimentId: UUID): Promise<Experiment> {
  return post<Experiment>(`/experiments/${experimentId}/activate`)
}

export async function selectWinner(experimentId: UUID): Promise<Experiment> {
  return post<Experiment>(`/experiments/${experimentId}/select-winner`)
}

export async function setWinner(experimentId: UUID, variantGroup: string): Promise<Experiment> {
  return post<Experiment>(`/experiments/${experimentId}/set-winner`, {
    variant_group: variantGroup,
  })
}

export async function promoteWinner(experimentId: UUID): Promise<{ promoted_asset_id: UUID }> {
  return post<{ promoted_asset_id: UUID }>(`/experiments/${experimentId}/promote`)
}
