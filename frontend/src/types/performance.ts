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
