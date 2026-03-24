import type {
  PricingAssessment,
  RankedSupplierPath,
} from './candidates'
import type { UUID } from './common'

export interface Product {
  id: UUID
  internal_sku: string | null
  title: string
  category: string | null
  source_platform: string
  source_product_id: string | null
  platform_price: number | null
  lifecycle_status: string | null
  status: string
  created_at: string
  updated_at: string | null
  assets_count: number
  listings_count: number
}

export interface ProductDetail {
  id: UUID
  internal_sku: string | null
  title: string
  category: string | null
  source_platform: string
  source_product_id: string | null
  source_url: string | null
  platform_price: number | null
  sales_count: number | null
  rating: number | null
  main_image_url: string | null
  lifecycle_status: string | null
  status: string
  created_at: string
  updated_at: string | null
  assets: ProductAsset[]
  listings: ProductListing[]
  supplier_matches: ProductSupplier[]
  pricing_assessment: PricingAssessment | null
}

export interface ProductAsset {
  id: UUID
  asset_type: string
  file_url: string
  style_tags: string[]
  human_approved: boolean
  ai_quality_score: number | null
}

export interface ProductListing {
  id: UUID
  platform: string
  region: string
  platform_listing_id: string | null
  price: number
  currency: string
  inventory: number
  status: string
  sync_error: string | null
}

export interface ProductSupplier {
  id: UUID
  supplier_name: string
  supplier_url: string
  supplier_sku: string | null
  supplier_price: number | null
  moq: number | null
  selected: boolean
  confidence_score: number | null
}

export interface ProductRankedSupplierPath extends RankedSupplierPath {}

export interface ListProductsResponse {
  total: number
  products: Product[]
}

export interface ProductStatsResponse {
  total_products: number
  by_lifecycle: Record<string, number>
  by_status: Record<string, number>
  total_assets: number
  total_listings: number
  total_published: number
}
