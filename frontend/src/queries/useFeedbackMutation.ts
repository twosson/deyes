import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { post } from '@/api/http'

export interface CreateFeedbackPayload {
  action: 'accepted' | 'rejected' | 'deferred'
  comment?: string
}

export function useCreateFeedbackMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      candidateId,
      payload,
    }: {
      candidateId: string
      payload: CreateFeedbackPayload
    }) => {
      return await post(
        `/api/recommendations/${candidateId}/feedback`,
        payload,
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
      queryClient.invalidateQueries({ queryKey: ['recommendation-feedback-stats'] })
    },
  })
}
