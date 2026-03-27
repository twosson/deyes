import type { ListRecommendationsParams } from '@/types/recommendations'
import type { UUID } from '@/types/common'

import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import {
  getCandidateRecommendation,
  getRecommendationStatsOverview,
  listRecommendations,
} from '@/api/recommendations'

export function useRecommendationsQuery(params?: MaybeRefOrGetter<ListRecommendationsParams>) {
  return useQuery({
    queryKey: computed(() => ['recommendations', toValue(params)]),
    queryFn: () => listRecommendations(toValue(params)),
  })
}

export function useCandidateRecommendationQuery(candidateId: MaybeRefOrGetter<UUID | null | undefined>) {
  return useQuery({
    queryKey: computed(() => ['candidate-recommendation', toValue(candidateId)]),
    queryFn: () => getCandidateRecommendation(toValue(candidateId) as UUID),
    enabled: computed(() => !!toValue(candidateId)),
  })
}

export function useRecommendationStatsOverviewQuery() {
  return useQuery({
    queryKey: ['recommendations', 'stats', 'overview'],
    queryFn: getRecommendationStatsOverview,
  })
}
