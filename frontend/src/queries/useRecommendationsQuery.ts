import type { ListRecommendationsParams } from '@/types/recommendations'
import type { UUID } from '@/types/common'

import { useQuery } from '@tanstack/vue-query'

import { getCandidateRecommendation, listRecommendations } from '@/api/recommendations'

export function useRecommendationsQuery(params?: ListRecommendationsParams) {
  return useQuery({
    queryKey: ['recommendations', params],
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
