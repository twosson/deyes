import type { UUID } from '@/types/common'
import type {
  AssetPerformanceDaily,
  AssetPerformanceRow,
  AutoActionHistoryItem,
  DashboardListResponse,
  ListingPerformanceDaily,
  ListingPerformanceRow,
  PerformanceMetrics,
  PerformanceOverview,
} from '@/types/performance'

import { get } from './http'

export interface GetAssetPerformanceParams {
  start_date?: string
  end_date?: string
  listing_id?: UUID
}

export interface GetListingPerformanceParams {
  start_date?: string
  end_date?: string
}

export interface GetPerformanceTrendsParams {
  asset_ids?: UUID[]
  listing_ids?: UUID[]
  start_date?: string
  end_date?: string
  granularity?: 'daily' | 'weekly' | 'monthly'
}

export interface PerformanceTrend {
  date: string
  impressions: number
  clicks: number
  orders: number
  revenue: number
}

export async function getAssetPerformance(
  assetId: UUID,
  params?: GetAssetPerformanceParams
): Promise<AssetPerformanceDaily[]> {
  return get<AssetPerformanceDaily[]>(`/performance/assets/${assetId}`, { params })
}

export async function getListingPerformance(
  listingId: UUID,
  params?: GetListingPerformanceParams
): Promise<ListingPerformanceDaily[]> {
  return get<ListingPerformanceDaily[]>(`/performance/listings/${listingId}`, { params })
}

export async function getPerformanceTrends(
  params?: GetPerformanceTrendsParams
): Promise<PerformanceTrend[]> {
  return get<PerformanceTrend[]>('/performance/trends', { params })
}

export async function getAssetPerformanceSummary(assetId: UUID): Promise<PerformanceMetrics> {
  return get<PerformanceMetrics>(`/performance/assets/${assetId}/summary`)
}

export async function getPerformanceOverview(): Promise<PerformanceOverview> {
  return get<PerformanceOverview>('/performance/dashboard/overview')
}

export async function getDashboardListings(limit = 20): Promise<DashboardListResponse<ListingPerformanceRow>> {
  return get<DashboardListResponse<ListingPerformanceRow>>('/performance/dashboard/listings', {
    params: { limit },
  })
}

export async function getDashboardAssets(limit = 20): Promise<DashboardListResponse<AssetPerformanceRow>> {
  return get<DashboardListResponse<AssetPerformanceRow>>('/performance/dashboard/assets', {
    params: { limit },
  })
}

export async function getRecentAutoActions(limit = 20): Promise<DashboardListResponse<AutoActionHistoryItem>> {
  return get<DashboardListResponse<AutoActionHistoryItem>>('/performance/dashboard/recent-actions', {
    params: { limit },
  })
}
