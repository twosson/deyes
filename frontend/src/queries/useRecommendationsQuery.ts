import type { ListRecommendationsParams } from '@/types/recommendations'
import type { UUID } from '@/types/common'

import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import {
  getCandidateRecommendation,
  getRecommendationStatsOverview,
  listRecommendations,
} from '@/api/recommendations'

export function useRecommendationsQuery(params?: ListRecommendationsParams) {
  return useQuery({
    queryKey: computed(() => ['recommendations', params]),
    queryFn: () => listRecommendations(params),
  })
}

export function useCandidateRecommendationQuery(candidateId: UUID) {
  return useQuery({
    queryKey: ['candidate-recommendation', candidateId],
    queryFn: () => getCandidateRecommendation(candidateId),
    enabled: !!candidateId,
  })
}

export function useRecommendationStatsOverviewQuery() {
  return useQuery({
    queryKey: ['recommendations', 'stats', 'overview'],
    queryFn: getRecommendationStatsOverview,
  })
}
