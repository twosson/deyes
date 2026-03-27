import type {
  CandidateRecommendation,
  FeedbackStatsResponse,
  ListRecommendationsParams,
  ListRecommendationsResponse,
  PlatformComparisonResponse,
  RecommendationStatsOverview,
  RecommendationTrendsResponse,
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

export async function getRecommendationStatsOverview(): Promise<RecommendationStatsOverview> {
  return get<RecommendationStatsOverview>('/recommendations/stats/overview')
}

export async function getRecommendationTrends(params?: {
  period?: 'day' | 'week' | 'month'
  days?: number
  min_score?: number
}): Promise<RecommendationTrendsResponse> {
  const searchParams = new URLSearchParams()

  if (params?.period) searchParams.append('period', params.period)
  if (params?.days) searchParams.append('days', params.days.toString())
  if (params?.min_score !== undefined)
    searchParams.append('min_score', params.min_score.toString())

  const query = searchParams.toString()
  const url = query ? `/recommendations/stats/trends?${query}` : '/recommendations/stats/trends'

  return get<RecommendationTrendsResponse>(url)
}

export async function getRecommendationsByPlatform(params?: {
  min_score?: number
}): Promise<PlatformComparisonResponse> {
  const searchParams = new URLSearchParams()

  if (params?.min_score !== undefined)
    searchParams.append('min_score', params.min_score.toString())

  const query = searchParams.toString()
  const url = query
    ? `/recommendations/stats/by-platform?${query}`
    : '/recommendations/stats/by-platform'

  return get<PlatformComparisonResponse>(url)
}

export async function getRecommendationFeedbackStats(params?: {
  days?: number
}): Promise<FeedbackStatsResponse> {
  const searchParams = new URLSearchParams()

  if (params?.days) searchParams.append('days', params.days.toString())

  const query = searchParams.toString()
  const url = query
    ? `/recommendations/stats/feedback?${query}`
    : '/recommendations/stats/feedback'

  return get<FeedbackStatsResponse>(url)
}
