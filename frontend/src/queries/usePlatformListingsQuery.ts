import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import type { MaybeRef } from 'vue'
import { computed, unref } from 'vue'

import {
  delistListing,
  getListingStatusDistribution,
  listPlatformListings,
  pauseListing,
  publishToPlatforms,
  resumeListing,
  syncInventory,
} from '@/api/platformListings'
import { getErrorMessage } from '@/api/http'
import type { UUID } from '@/types/common'
import type { PublishRequest } from '@/types/platformListings'

export function usePlatformListingsQuery(params?: MaybeRef<Record<string, unknown>>) {
  return useQuery({
    queryKey: computed(() => ['platform-listings', unref(params)]),
    queryFn: () => listPlatformListings(unref(params)),
    placeholderData: keepPreviousData,
  })
}

export function useListingStatusDistributionQuery() {
  return useQuery({
    queryKey: ['platform-listings', 'stats', 'distribution'],
    queryFn: getListingStatusDistribution,
  })
}

export function usePublishMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: PublishRequest) => publishToPlatforms(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-listings'] })
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      message.success('发布任务已提交')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

export function usePauseListingMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (listingId: UUID) => pauseListing(listingId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-listings'] })
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      message.success('Listing 已暂停')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

export function useResumeListingMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (listingId: UUID) => resumeListing(listingId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-listings'] })
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      message.success('Listing 已恢复')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

export function useDelistListingMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (listingId: UUID) => delistListing(listingId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-listings'] })
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      message.success('Listing 已下架')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}

export function useSyncInventoryMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (platform_listing_ids?: UUID[]) => syncInventory(platform_listing_ids),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-listings'] })
      message.success('库存同步已完成')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}
