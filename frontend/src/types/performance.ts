import type { UUID } from './common'

export interface BasePerformanceDaily {
  id: UUID
  metric_date: string
  impressions: number
  clicks: number
  orders: number
  units_sold: number
  revenue: number | null
  ad_spend: number | null
  returns_count: number
  refund_amount: number | null
  created_at: string
  updated_at: string
}

export interface ListingPerformanceDaily extends BasePerformanceDaily {
  listing_id: UUID
}

export interface AssetPerformanceDaily extends BasePerformanceDaily {
  asset_id: UUID
  listing_id: UUID
}

export interface PerformanceMetrics {
  impressions: number
  clicks: number
  orders: number
  units_sold: number
  revenue: number
  ad_spend: number
  returns_count: number
  refund_amount: number
  ctr: number
  cvr: number
  roas?: number
  avg_order_value: number
}

export interface PerformanceOverview {
  active_listings_count: number
  tracked_listings_count: number
  low_roi_alerts: number
  low_ctr_alerts: number
}

export interface ListingPerformanceRow {
  listing_id: UUID
  platform: string
  region: string
  platform_listing_id: string | null
  price: number
  currency: string
  status: string
  impressions: number
  clicks: number
  orders: number
  revenue: number
  ad_spend: number
  ctr: number
  cvr: number
  roi: number
  roas: number
}

export interface AssetPerformanceRow {
  asset_id: UUID
  asset_type: string
  file_url: string
  ai_quality_score: number | null
  impressions: number
  clicks: number
  orders: number
  revenue: number
  ctr: number
  cvr: number
}

export interface AutoActionHistoryItem {
  event_id: UUID
  event_type: string
  listing_id: UUID | null
  created_at: string | null
  payload: Record<string, unknown>
}

export interface DashboardListResponse<T> {
  items: T[]
  count: number
}
