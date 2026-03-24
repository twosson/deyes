import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import type { MaybeRef } from 'vue'
import { computed, unref } from 'vue'

import { approveAsset, generateAssets, getAssetTypeDistribution, listAssets, rejectAsset } from '@/api/contentAssets'
import { getErrorMessage } from '@/api/http'
import type { UUID } from '@/types/common'
import type { GenerateAssetsRequest } from '@/types/contentAssets'

export function useContentAssetsQuery(params?: MaybeRef<Record<string, unknown>>) {
  return useQuery({
    queryKey: computed(() => ['content-assets', unref(params)]),
    queryFn: () => listAssets(unref(params)),
    placeholderData: keepPreviousData,
  })
}

export function useAssetTypeDistributionQuery() {
  return useQuery({
    queryKey: ['content-assets', 'stats', 'distribution'],
    queryFn: getAssetTypeDistribution,
  })
}

export function useApproveAssetMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ assetId, notes }: { assetId: UUID; notes?: string }) => approveAsset(assetId, notes),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['content-assets'] })
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      message.success('素材已通过审核')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

export function useRejectAssetMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ assetId, notes }: { assetId: UUID; notes?: string }) => rejectAsset(assetId, notes),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['content-assets'] })
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      message.success('素材已驳回')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

export function useGenerateAssetsMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: GenerateAssetsRequest) => generateAssets(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['content-assets'] })
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      message.success('素材生成任务已提交')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}
