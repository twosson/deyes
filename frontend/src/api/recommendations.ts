import type {
  CandidateRecommendation,
  ListRecommendationsParams,
  ListRecommendationsResponse,
} from '@/types/recommendations'
import type { UUID } from '@/types/common'

import { get } from './http'

export async function listRecommendations(
  params?: ListRecommendationsParams,
): Promise<ListRecommendationsResponse> {
  const searchParams = new URLSearchParams()

  if (params?.limit) searchParams.append('limit', params.limit.toString())
  if (params?.category) searchParams.append('category', params.category)
  if (params?.min_score !== undefined)
    searchParams.append('min_score', params.min_score.toString())
  if (params?.risk_level) searchParams.append('risk_level', params.risk_level)

  const query = searchParams.toString()
  const url = query ? `/recommendations?${query}` : '/recommendations'

  return get<ListRecommendationsResponse>(url)
}

export async function getCandidateRecommendation(
  candidateId: UUID,
): Promise<CandidateRecommendation> {
  return get<CandidateRecommendation>(`/candidates/${candidateId}/recommendation`)
}
