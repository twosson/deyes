<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

import { formatCurrency } from '@/adapters/formatters'
import { listingStatusMeta } from '@/adapters/statusMeta'
import { useCandidatesQuery } from '@/queries/useCandidatesQuery'
import {
  useDelistListingMutation,
  usePauseListingMutation,
  usePlatformListingsQuery,
  usePublishMutation,
  useResumeListingMutation,
  useSyncInventoryMutation,
} from '@/queries/usePlatformListingsQuery'

const publishOpen = ref(false)
const filters = reactive({
  platform: '',
  region: '',
  status: undefined as string | undefined,
  limit: 10,
  offset: 0,
})
const publishForm = reactive({
  candidate_product_id: undefined as string | undefined,
  platform: 'temu',
  region: 'us',
  pricing_strategy: 'standard',
  auto_approve: false,
})

const queryParams = computed(() => ({
  platform: filters.platform || undefined,
  region: filters.region || undefined,
  status: filters.status,
  limit: filters.limit,
  offset: filters.offset,
}))

const listingsQuery = usePlatformListingsQuery(queryParams)
const candidatesQuery = useCandidatesQuery()
const publishMutation = usePublishMutation()
const pauseMutation = usePauseListingMutation()
const resumeMutation = useResumeListingMutation()
const delistMutation = useDelistListingMutation()
const syncMutation = useSyncInventoryMutation()

const rows = computed(() => listingsQuery.data.value?.listings ?? [])
const total = computed(() => listingsQuery.data.value?.total ?? 0)
const candidateOptions = computed(() =>
  (candidatesQuery.data.value?.items ?? []).map((item) => ({ value: item.id, label: item.title }))
)
const listingTag = (status?: string | null) => listingStatusMeta[status ?? ''] ?? { label: status ?? '--', color: 'default' }

async function handlePause(listingId: string) {
  await pauseMutation.mutateAsync(listingId)
}

async function handleResume(listingId: string) {
  await resumeMutation.mutateAsync(listingId)
}

async function handleDelist(listingId: string) {
  await delistMutation.mutateAsync(listingId)
}

async function handleSync(listingId?: string) {
  await syncMutation.mutateAsync(listingId ? [listingId] : undefined)
}

async function handlePublish() {
  if (!publishForm.candidate_product_id) {
    return
  }

  await publishMutation.mutateAsync({
    candidate_product_id: publishForm.candidate_product_id,
    target_platforms: [
      {
        platform: publishForm.platform,
        region: publishForm.region,
      },
    ],
    pricing_strategy: publishForm.pricing_strategy,
    auto_approve: publishForm.auto_approve,
  })
  publishOpen.value = false
}

function handlePageChange(page: number, size: number) {
  filters.limit = size
  filters.offset = (page - 1) * size
}
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="发布中心">
      <template #extra>
        <a-button type="primary" @click="publishOpen = true">发布到平台</a-button>
      </template>

      <div class="filter-grid">
        <a-input v-model:value="filters.platform" placeholder="平台，如 temu / amazon" allow-clear />
        <a-input v-model:value="filters.region" placeholder="区域，如 us" allow-clear />
        <a-select
          v-model:value="filters.status"
          allow-clear
          placeholder="状态"
          :options="Object.entries(listingStatusMeta).map(([value, meta]) => ({ value, label: meta.label }))"
        />
        <a-space>
          <a-button type="primary" @click="listingsQuery.refetch()">查询</a-button>
          <a-button @click="handleSync()" :loading="syncMutation.isPending.value">同步全部库存</a-button>
        </a-space>
      </div>
    </a-card>

    <a-card class="section-card" title="平台 listing 列表">
      <a-table :data-source="rows" :loading="listingsQuery.isLoading.value" :pagination="false" row-key="id">
        <a-table-column title="平台" data-index="platform" key="platform" :width="120" />
        <a-table-column title="区域" data-index="region" key="region" :width="90" />
        <a-table-column title="平台 ID" data-index="platform_listing_id" key="platform_listing_id" :width="150" />
        <a-table-column title="价格" key="price" :width="120">
          <template #default="{ record }">{{ formatCurrency(record.price, record.currency) }}</template>
        </a-table-column>
        <a-table-column title="库存" data-index="inventory" key="inventory" :width="90" />
        <a-table-column title="状态" key="status" :width="120">
          <template #default="{ record }">
            <a-tag :color="listingTag(record.status).color">{{ listingTag(record.status).label }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="同步状态" key="sync_status" :width="110">
          <template #default="{ record }">{{ record.sync_status ?? '--' }}</template>
        </a-table-column>
        <a-table-column title="同步错误" data-index="sync_error" key="sync_error" :width="220" ellipsis />
        <a-table-column title="操作" key="actions" :width="220" fixed="right">
          <template #default="{ record }">
            <a-space>
              <a-button size="small" @click="handleSync(record.id)">同步</a-button>
              <a-button v-if="record.status !== 'paused'" size="small" @click="handlePause(record.id)">暂停</a-button>
              <a-button v-else size="small" @click="handleResume(record.id)">恢复</a-button>
              <a-button size="small" danger @click="handleDelist(record.id)">下架</a-button>
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

    <a-modal
      v-model:open="publishOpen"
      title="发布到平台"
      ok-text="开始发布"
      cancel-text="取消"
      :confirm-loading="publishMutation.isPending.value"
      @ok="handlePublish"
    >
      <div class="page-stack">
        <a-select
          v-model:value="publishForm.candidate_product_id"
          show-search
          placeholder="选择商品"
          :options="candidateOptions"
        />
        <a-input v-model:value="publishForm.platform" placeholder="目标平台，如 temu / amazon" />
        <a-input v-model:value="publishForm.region" placeholder="区域，如 us / uk / de" />
        <a-select
          v-model:value="publishForm.pricing_strategy"
          :options="[
            { value: 'standard', label: '标准' },
            { value: 'aggressive', label: '激进' },
            { value: 'premium', label: '高毛利' },
          ]"
        />
        <a-switch v-model:checked="publishForm.auto_approve" checked-children="自动" un-checked-children="人工" />
      </div>
    </a-modal>
  </div>
</template>
