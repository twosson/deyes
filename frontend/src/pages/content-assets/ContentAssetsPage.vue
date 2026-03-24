<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

import { assetTypeLabel } from '@/adapters/statusMeta'
import { useCandidatesQuery } from '@/queries/useCandidatesQuery'
import {
  useApproveAssetMutation,
  useContentAssetsQuery,
  useGenerateAssetsMutation,
  useRejectAssetMutation,
} from '@/queries/useContentAssetsQuery'

const generationOpen = ref(false)
const filters = reactive({
  candidate_product_id: undefined as string | undefined,
  asset_type: undefined as string | undefined,
  approved: undefined as boolean | undefined,
  style: '',
  platform: '',
  region: '',
  limit: 24,
  offset: 0,
})

const generationForm = reactive({
  candidate_product_id: undefined as string | undefined,
  asset_types: ['main_image'],
  styles: ['minimalist'],
  generate_count: 1,
  platforms: [] as string[],
  regions: [] as string[],
})

const queryParams = computed(() => ({
  candidate_product_id: filters.candidate_product_id,
  asset_type: filters.asset_type,
  approved: filters.approved,
  style: filters.style || undefined,
  platform: filters.platform || undefined,
  region: filters.region || undefined,
  limit: filters.limit,
  offset: filters.offset,
}))

const assetsQuery = useContentAssetsQuery(queryParams)
const candidatesQuery = useCandidatesQuery()
const approveMutation = useApproveAssetMutation()
const rejectMutation = useRejectAssetMutation()
const generateMutation = useGenerateAssetsMutation()

const assets = computed(() => assetsQuery.data.value?.assets ?? [])
const total = computed(() => assetsQuery.data.value?.total ?? 0)
const candidateOptions = computed(() =>
  (candidatesQuery.data.value?.items ?? []).map((item) => ({ value: item.id, label: item.title }))
)
const assetLabel = (assetType?: string | null) => assetTypeLabel[assetType ?? ''] ?? assetType ?? '--'

async function handleApprove(assetId: string) {
  await approveMutation.mutateAsync({ assetId })
}

async function handleReject(assetId: string) {
  await rejectMutation.mutateAsync({ assetId })
}

async function handleGenerateAssets() {
  if (!generationForm.candidate_product_id) {
    return
  }

  await generateMutation.mutateAsync({
    candidate_product_id: generationForm.candidate_product_id,
    asset_types: generationForm.asset_types,
    styles: generationForm.styles,
    generate_count: generationForm.generate_count,
    platforms: generationForm.platforms,
    regions: generationForm.regions,
  })
  generationOpen.value = false
}

function handlePageChange(page: number, size: number) {
  filters.limit = size
  filters.offset = (page - 1) * size
}
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="内容中心">
      <template #extra>
        <a-button type="primary" @click="generationOpen = true">发起素材生成</a-button>
      </template>

      <div class="filter-grid">
        <a-select
          v-model:value="filters.candidate_product_id"
          allow-clear
          show-search
          placeholder="商品"
          :options="candidateOptions"
        />
        <a-select
          v-model:value="filters.asset_type"
          allow-clear
          placeholder="素材类型"
          :options="Object.entries(assetTypeLabel).map(([value, label]) => ({ value, label }))"
        />
        <a-select
          v-model:value="filters.approved"
          allow-clear
          placeholder="审核状态"
          :options="[
            { value: true, label: '已通过' },
            { value: false, label: '未通过' },
          ]"
        />
        <a-input v-model:value="filters.style" placeholder="风格标签" allow-clear />
        <a-input v-model:value="filters.platform" placeholder="平台标签" allow-clear />
        <a-input v-model:value="filters.region" placeholder="地区标签" allow-clear />
        <a-button type="primary" @click="assetsQuery.refetch()">查询</a-button>
      </div>
    </a-card>

    <a-card class="section-card" title="素材列表">
      <a-row :gutter="16">
        <a-col v-for="asset in assets" :key="asset.id" :xs="24" :sm="12" :lg="8" :xl="6" style="margin-bottom: 16px">
          <a-card hoverable>
            <template #cover>
              <div class="asset-card-cover">
                <img :src="asset.file_url" :alt="asset.asset_type" />
              </div>
            </template>
            <a-card-meta :title="assetLabel(asset.asset_type)" :description="asset.style_tags?.join(' / ') || '未标注风格'" />
            <div class="panel-stack" style="margin-top: 12px">
              <a-space wrap>
                <a-tag>{{ asset.human_approved ? '已通过' : '未通过' }}</a-tag>
                <a-tag color="blue">质量分 {{ asset.ai_quality_score ?? '--' }}</a-tag>
              </a-space>
              <a-space wrap>
                <a-button size="small" type="primary" @click="handleApprove(asset.id)">通过</a-button>
                <a-button size="small" danger @click="handleReject(asset.id)">驳回</a-button>
                <a :href="asset.file_url" target="_blank" rel="noreferrer">查看原图</a>
              </a-space>
            </div>
          </a-card>
        </a-col>
      </a-row>

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
      v-model:open="generationOpen"
      title="发起素材生成"
      ok-text="开始生成"
      cancel-text="取消"
      :confirm-loading="generateMutation.isPending.value"
      @ok="handleGenerateAssets"
    >
      <div class="page-stack">
        <a-select
          v-model:value="generationForm.candidate_product_id"
          show-search
          placeholder="选择商品"
          :options="candidateOptions"
        />
        <a-select
          v-model:value="generationForm.asset_types"
          mode="multiple"
          placeholder="素材类型"
          :options="Object.entries(assetTypeLabel).map(([value, label]) => ({ value, label }))"
        />
        <a-select
          v-model:value="generationForm.styles"
          mode="tags"
          placeholder="风格，如 minimalist / luxury"
        />
        <a-input-number v-model:value="generationForm.generate_count" :min="1" :max="5" style="width: 100%" />
        <a-select v-model:value="generationForm.platforms" mode="tags" placeholder="平台标签，如 temu / amazon" />
        <a-select v-model:value="generationForm.regions" mode="tags" placeholder="地区标签，如 us / uk / de" />
      </div>
    </a-modal>
  </div>
</template>
