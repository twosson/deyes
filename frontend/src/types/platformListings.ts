import type { UUID } from './common'

export interface PlatformListing {
  id: UUID
  candidate_product_id: UUID
  platform: string
  region: string
  platform_listing_id: string | null
  platform_url: string | null
  price: number
  currency: string
  inventory: number
  status: string
  total_sales: number
  total_revenue: number | null
  created_at: string
  last_synced_at: string | null
  sync_error: string | null
  sync_status: string | null
  platform_synced: boolean | null
}

export interface ListPlatformListingsResponse {
  total: number
  listings: PlatformListing[]
}

export interface PublishRequest {
  candidate_product_id: UUID
  target_platforms: Array<{
    platform: string
    region: string
  }>
  pricing_strategy?: string
  auto_approve?: boolean
}
