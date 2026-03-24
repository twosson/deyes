import { useQuery } from '@tanstack/vue-query'
import type { MaybeRef } from 'vue'
import { computed, unref } from 'vue'

import { getCandidateDetail, listCandidates } from '@/api/candidates'
import type { UUID } from '@/types/common'

export function useCandidatesQuery() {
  return useQuery({
    queryKey: ['candidates'],
    queryFn: listCandidates,
  })
}

export function useCandidateDetailQuery(candidateId: MaybeRef<UUID | null | undefined>) {
  return useQuery({
    queryKey: computed(() => ['candidates', unref(candidateId)]),
    queryFn: () => getCandidateDetail(unref(candidateId) as UUID),
    enabled: computed(() => !!unref(candidateId)),
  })
}
