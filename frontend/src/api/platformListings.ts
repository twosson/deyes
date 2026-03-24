import type { UUID } from '@/types/common'
import type { ListPlatformListingsResponse, PublishRequest } from '@/types/platformListings'

import { del, get, post } from './http'

export interface ListListingsParams {
  platform?: string
  region?: string
  status?: string
  limit?: number
  offset?: number
}

export async function listPlatformListings(params?: ListListingsParams): Promise<ListPlatformListingsResponse> {
  return get<ListPlatformListingsResponse>('/platform-listings', { params })
}

export async function getListingStatusDistribution(): Promise<Record<string, number>> {
  return get<Record<string, number>>('/platform-listings/stats/distribution')
}

export async function publishToPlatforms(payload: PublishRequest) {
  return post('/platform-listings/publish', payload)
}

export async function pauseListing(listingId: UUID) {
  return post(`/platform-listings/${listingId}/pause`)
}

export async function resumeListing(listingId: UUID) {
  return post(`/platform-listings/${listingId}/resume`)
}

export async function delistListing(listingId: UUID) {
  return del(`/platform-listings/${listingId}`)
}

export async function syncInventory(platform_listing_ids?: UUID[]) {
  return post('/platform-listings/sync-inventory', { platform_listing_ids })
}
