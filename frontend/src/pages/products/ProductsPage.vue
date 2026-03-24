<script setup lang="ts">
import { ReloadOutlined } from '@ant-design/icons-vue'
import { computed, reactive } from 'vue'
import { useRouter } from 'vue-router'

import { formatCurrency, formatDateTime } from '@/adapters/formatters'
import { candidateStatusMeta, lifecycleMeta, sourcePlatformLabel } from '@/adapters/statusMeta'
import { useProductsQuery, useUpdateProductLifecycleMutation } from '@/queries/useProductsQuery'
import type { Product } from '@/types/products'

const router = useRouter()
const pageSize = 10
const filters = reactive({
  search: '',
  lifecycle_status: undefined as string | undefined,
  status: undefined as string | undefined,
  category: '',
  limit: pageSize,
  offset: 0,
})

const queryParams = computed(() => ({
  search: filters.search || undefined,
  lifecycle_status: filters.lifecycle_status,
  status: filters.status,
  category: filters.category || undefined,
  limit: filters.limit,
  offset: filters.offset,
}))

const productsQuery = useProductsQuery(queryParams)
const updateLifecycleMutation = useUpdateProductLifecycleMutation()

const rows = computed(() => productsQuery.data.value?.products ?? [])
const total = computed(() => productsQuery.data.value?.total ?? 0)

const lifecycleTag = (status?: string | null) => lifecycleMeta[status ?? ''] ?? { label: status ?? '--', color: 'default' }
const candidateTag = (status?: string | null) => candidateStatusMeta[status ?? ''] ?? { label: status ?? '--', color: 'default' }
const sourceLabel = (source?: string) => sourcePlatformLabel[source ?? ''] ?? source ?? '--'

async function handleLifecycleChange(product: Product, lifecycle: string) {
  await updateLifecycleMutation.mutateAsync({
    productId: product.id,
    lifecycle_status: lifecycle,
  })
}

function handlePageChange(page: number, size: number) {
  filters.limit = size
  filters.offset = (page - 1) * size
}

function openProduct(record: Product) {
  void router.push(`/products/${record.id}`)
}
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="商品中心">
      <div class="filter-grid">
        <a-input-search v-model:value="filters.search" placeholder="搜索商品标题" allow-clear />
        <a-select
          v-model:value="filters.lifecycle_status"
          allow-clear
          placeholder="生命周期"
          :options="Object.entries(lifecycleMeta).map(([value, meta]) => ({ value, label: meta.label }))"
        />
        <a-select
          v-model:value="filters.status"
          allow-clear
          placeholder="候选状态"
          :options="Object.entries(candidateStatusMeta).map(([value, meta]) => ({ value, label: meta.label }))"
        />
        <a-input v-model:value="filters.category" placeholder="类目" allow-clear />
        <a-space>
          <a-button type="primary" @click="productsQuery.refetch()">查询</a-button>
          <a-button @click="productsQuery.refetch()">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
        </a-space>
      </div>
    </a-card>

    <a-card class="section-card" title="商品列表">
      <a-table :data-source="rows" :loading="productsQuery.isLoading.value" :pagination="false" row-key="id">
        <a-table-column title="商品标题" data-index="title" key="title" :width="280" ellipsis />
        <a-table-column title="来源" key="source_platform" :width="100">
          <template #default="{ record }">{{ sourceLabel(record.source_platform) }}</template>
        </a-table-column>
        <a-table-column title="类目" data-index="category" key="category" :width="120" />
        <a-table-column title="平台价" key="platform_price" :width="120">
          <template #default="{ record }">{{ formatCurrency(record.platform_price) }}</template>
        </a-table-column>
        <a-table-column title="生命周期" key="lifecycle_status" :width="120">
          <template #default="{ record }">
            <a-tag :color="lifecycleTag(record.lifecycle_status).color">{{ lifecycleTag(record.lifecycle_status).label }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="候选状态" key="status" :width="120">
          <template #default="{ record }">
            <a-tag :color="candidateTag(record.status).color">{{ candidateTag(record.status).label }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="素材数" data-index="assets_count" key="assets_count" :width="90" />
        <a-table-column title="发布数" data-index="listings_count" key="listings_count" :width="90" />
        <a-table-column title="创建时间" key="created_at" :width="150">
          <template #default="{ record }">{{ formatDateTime(record.created_at) }}</template>
        </a-table-column>
        <a-table-column title="操作" key="actions" :width="220" fixed="right">
          <template #default="{ record }">
            <a-space>
              <a-button type="link" @click="openProduct(record)">详情</a-button>
              <a-dropdown>
                <a-button type="link">流转</a-button>
                <template #overlay>
                  <a-menu>
                    <a-menu-item
                      v-for="(meta, key) in lifecycleMeta"
                      :key="key"
                      @click="handleLifecycleChange(record, key)"
                    >
                      {{ meta.label }}
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </a-space>
          </template>
        </a-table-column>
      </a-table>

      <div style="display: flex; justify-content: flex-end; margin-top: 16px">
        <a-pagination
          :current="Math.floor(filters.offset / filters.limit) + 1"
          :page-size="filters.limit"
          :total="total"
          show-size-changer
          @change="handlePageChange"
        />
      </div>
    </a-card>
  </div>
</template>
