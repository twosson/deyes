import type { CandidateDetail, ListCandidatesResponse } from '@/types/candidates'
import type { UUID } from '@/types/common'

import { get } from './http'

export async function listCandidates(): Promise<ListCandidatesResponse> {
  return get<ListCandidatesResponse>('/candidates')
}

export async function getCandidateDetail(candidateId: UUID): Promise<CandidateDetail> {
  return get<CandidateDetail>(`/candidates/${candidateId}`)
}
