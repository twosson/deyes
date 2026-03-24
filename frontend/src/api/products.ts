import type { UUID } from '@/types/common'
import type {
  ListProductsResponse,
  ProductDetail,
  ProductStatsResponse,
} from '@/types/products'

import { get, patch } from './http'

export interface ListProductsParams {
  lifecycle_status?: string
  status?: string
  category?: string
  search?: string
  limit?: number
  offset?: number
}

export async function listProducts(params?: ListProductsParams): Promise<ListProductsResponse> {
  return get<ListProductsResponse>('/products', { params })
}

export async function getProductDetail(productId: UUID): Promise<ProductDetail> {
  return get<ProductDetail>(`/products/${productId}`)
}

export async function getProductStats(): Promise<ProductStatsResponse> {
  return get<ProductStatsResponse>('/products/stats/overview')
}

export async function updateProductLifecycle(
  productId: UUID,
  lifecycle_status: string
): Promise<{ success: boolean; product_id: string; lifecycle_status: string }> {
  return patch(`/products/${productId}/lifecycle`, { lifecycle_status })
}
