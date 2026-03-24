import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import type { MaybeRef } from 'vue'
import { computed, unref } from 'vue'

import type { ListProductsParams } from '@/api/products'
import {
  getProductDetail,
  getProductStats,
  listProducts,
  updateProductLifecycle,
} from '@/api/products'
import { getErrorMessage } from '@/api/http'
import type { UUID } from '@/types/common'

export function useProductsQuery(params?: MaybeRef<ListProductsParams>) {
  return useQuery({
    queryKey: computed(() => ['products', unref(params)]),
    queryFn: () => listProducts(unref(params)),
    placeholderData: keepPreviousData,
  })
}

export function useProductDetailQuery(productId: MaybeRef<UUID>) {
  return useQuery({
    queryKey: computed(() => ['products', unref(productId)]),
    queryFn: () => getProductDetail(unref(productId)),
    enabled: computed(() => !!unref(productId)),
  })
}

export function useProductStatsQuery() {
  return useQuery({
    queryKey: ['products', 'stats'],
    queryFn: getProductStats,
  })
}

export function useUpdateProductLifecycleMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ productId, lifecycle_status }: { productId: UUID; lifecycle_status: string }) =>
      updateProductLifecycle(productId, lifecycle_status),
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      void queryClient.invalidateQueries({ queryKey: ['products', variables.productId] })
      message.success('商品生命周期已更新')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })
}
