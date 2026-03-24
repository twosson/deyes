import type { UUID } from './common'

export interface ContentAsset {
  id: UUID
  candidate_product_id: UUID
  asset_type: string
  style_tags: string[]
  platform_tags: string[]
  region_tags: string[]
  file_url: string
  file_size: number | null
  dimensions: string | null
  format: string | null
  ai_quality_score: number | null
  human_approved: boolean
  usage_count: number
  version: number
  created_at: string
}

export interface ListAssetsResponse {
  total: number
  assets: ContentAsset[]
}

export interface GenerateAssetsRequest {
  candidate_product_id: UUID
  asset_types: string[]
  styles: string[]
  reference_images?: string[] | null
  generate_count?: number
  platforms?: string[]
  regions?: string[]
}
