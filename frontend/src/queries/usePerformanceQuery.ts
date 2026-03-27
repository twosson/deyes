import { useQuery, keepPreviousData } from '@tanstack/vue-query'
import type { MaybeRef } from 'vue'
import { computed, unref } from 'vue'

import type {
  GetAssetPerformanceParams,
  GetListingPerformanceParams,
  GetPerformanceTrendsParams,
} from '@/api/performance'
import {
  getAssetPerformance,
  getAssetPerformanceSummary,
  getDashboardAssets,
  getDashboardListings,
  getListingPerformance,
  getPerformanceOverview,
  getPerformanceTrends,
  getRecentAutoActions,
} from '@/api/performance'
import type { UUID } from '@/types/common'

export function useAssetPerformanceQuery(
  assetId: MaybeRef<UUID | null | undefined>,
  params?: MaybeRef<GetAssetPerformanceParams | undefined>
) {
  return useQuery({
    queryKey: computed(() => ['performance', 'assets', unref(assetId), unref(params)]),
    queryFn: () => getAssetPerformance(unref(assetId) as UUID, unref(params)),
    enabled: computed(() => !!unref(assetId)),
    placeholderData: keepPreviousData,
  })
}

export function useAssetPerformanceSummaryQuery(assetId: MaybeRef<UUID | null | undefined>) {
  return useQuery({
    queryKey: computed(() => ['performance', 'assets', unref(assetId), 'summary']),
    queryFn: () => getAssetPerformanceSummary(unref(assetId) as UUID),
    enabled: computed(() => !!unref(assetId)),
  })
}

export function useListingPerformanceQuery(
  listingId: MaybeRef<UUID | null | undefined>,
  params?: MaybeRef<GetListingPerformanceParams | undefined>
) {
  return useQuery({
    queryKey: computed(() => ['performance', 'listings', unref(listingId), unref(params)]),
    queryFn: () => getListingPerformance(unref(listingId) as UUID, unref(params)),
    enabled: computed(() => !!unref(listingId)),
    placeholderData: keepPreviousData,
  })
}

export function usePerformanceTrendsQuery(params?: MaybeRef<GetPerformanceTrendsParams | undefined>) {
  return useQuery({
    queryKey: computed(() => ['performance', 'trends', unref(params)]),
    queryFn: () => getPerformanceTrends(unref(params)),
    placeholderData: keepPreviousData,
  })
}

// Dashboard queries

export function usePerformanceOverviewQuery() {
  return useQuery({
    queryKey: ['performance', 'dashboard', 'overview'],
    queryFn: getPerformanceOverview,
  })
}

export function useDashboardListingsQuery(limit?: MaybeRef<number | undefined>) {
  return useQuery({
    queryKey: computed(() => ['performance', 'dashboard', 'listings', unref(limit)]),
    queryFn: () => getDashboardListings(unref(limit)),
  })
}

export function useDashboardAssetsQuery(limit?: MaybeRef<number | undefined>) {
  return useQuery({
    queryKey: computed(() => ['performance', 'dashboard', 'assets', unref(limit)]),
    queryFn: () => getDashboardAssets(unref(limit)),
  })
}

export function useRecentAutoActionsQuery(limit?: MaybeRef<number | undefined>) {
  return useQuery({
    queryKey: computed(() => ['performance', 'dashboard', 'recent-actions', unref(limit)]),
    queryFn: () => getRecentAutoActions(unref(limit)),
  })
}
