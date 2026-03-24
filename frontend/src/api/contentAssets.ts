import type { GenerateAssetsRequest, ListAssetsResponse } from '@/types/contentAssets'
import type { UUID } from '@/types/common'

import { get, post } from './http'

export interface ListAssetsParams {
  candidate_product_id?: UUID
  asset_type?: string
  style?: string
  platform?: string
  region?: string
  approved?: boolean
  limit?: number
  offset?: number
}

export async function listAssets(params?: ListAssetsParams): Promise<ListAssetsResponse> {
  return get<ListAssetsResponse>('/content-assets', { params })
}

export async function getAssetTypeDistribution(): Promise<Record<string, number>> {
  return get<Record<string, number>>('/content-assets/stats/distribution')
}

export async function approveAsset(assetId: UUID, notes?: string) {
  return post(`/content-assets/${assetId}/approve`, { notes })
}

export async function rejectAsset(assetId: UUID, notes?: string) {
  return post(`/content-assets/${assetId}/reject`, { notes })
}

export async function generateAssets(payload: GenerateAssetsRequest) {
  return post('/content-assets/generate', payload)
}
