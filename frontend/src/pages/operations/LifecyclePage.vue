<script setup lang="ts">
import { SearchOutlined } from '@ant-design/icons-vue'
import { computed, ref } from 'vue'

import LifecycleTimeline from '@/components/LifecycleTimeline.vue'
import { formatDateTime } from '@/adapters/formatters'
import { getSkuLifecycleStateMeta } from '@/adapters/statusMeta'
import {
  useClearanceCandidatesQuery,
  useLifecycleStateQuery,
  useScalingCandidatesQuery,
} from '@/queries/useOperationsQuery'
import type { UUID } from '@/types/common'

const skuInput = ref('')
const searchedSkuId = ref<UUID | null>(null)

const lifecycleQuery = useLifecycleStateQuery(searchedSkuId)
const scalingQuery = useScalingCandidatesQuery(computed(() => ({ limit: 50 })))
const clearanceQuery = useClearanceCandidatesQuery(computed(() => ({ limit: 50 })))

const lifecycleState = computed(() => lifecycleQuery.data.value)
const currentStateMeta = computed(() => getSkuLifecycleStateMeta(lifecycleState.value?.current_state))

const relatedScalingCandidates = computed(() => {
  if (!searchedSkuId.value) return scalingQuery.data.value ?? []
  return (scalingQuery.data.value ?? []).filter((item) => item.product_variant_id === searchedSkuId.value)
})

const relatedClearanceCandidates = computed(() => {
  if (!searchedSkuId.value) return clearanceQuery.data.value ?? []
  return (clearanceQuery.data.value ?? []).filter((item) => item.product_variant_id === searchedSkuId.value)
})

function handleSearch() {
  const value = skuInput.value.trim()
  searchedSkuId.value = value ? (value as UUID) : null
}
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="SKU 生命周期追踪">
      <div class="page-stack">
        <a-alert
          type="info"
          show-icon
          message="输入 SKU ID 查询当前生命周期状态，并查看该 SKU 是否在扩量或清退候选列表中。"
        />

        <div class="search-row">
          <a-input
            v-model:value="skuInput"
            placeholder="输入 SKU ID"
            allow-clear
            @press-enter="handleSearch"
          />
          <a-button type="primary" @click="handleSearch">
            <template #icon><SearchOutlined /></template>
            查询
          </a-button>
        </div>
      </div>
    </a-card>

    <a-card class="section-card" title="生命周期状态">
      <a-empty v-if="!searchedSkuId" description="请输入 SKU ID 后查询生命周期" />

      <div v-else class="page-stack">
        <a-skeleton v-if="lifecycleQuery.isLoading.value" active />

        <template v-else-if="lifecycleState">
          <a-descriptions :column="3" bordered size="small">
            <a-descriptions-item label="SKU ID" :span="3">
              <span class="monospace-text">{{ lifecycleState.product_variant_id }}</span>
            </a-descriptions-item>
            <a-descriptions-item label="当前状态">
              <a-tag :color="currentStateMeta.color">{{ currentStateMeta.label }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="进入时间">
              {{ formatDateTime(lifecycleState.entered_at) }}
            </a-descriptions-item>
            <a-descriptions-item label="置信度">
              {{ lifecycleState.confidence_score.toFixed(2) }}
            </a-descriptions-item>
          </a-descriptions>

          <LifecycleTimeline
            :current-state="lifecycleState.current_state"
            :entered-at="lifecycleState.entered_at"
            :confidence-score="lifecycleState.confidence_score"
          />
        </template>

        <a-empty v-else description="未找到该 SKU 的生命周期信息" />
      </div>
    </a-card>

    <div class="two-column-grid">
      <a-card class="section-card" title="扩量候选">
        <a-list :data-source="relatedScalingCandidates" :loading="scalingQuery.isLoading.value">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>
                  <span class="monospace-text">{{ item.product_variant_id }}</span>
                </template>
                <template #description>
                  <div class="candidate-meta">
                    <div>状态：{{ getSkuLifecycleStateMeta(item.current_state).label }}</div>
                    <div>进入时间：{{ formatDateTime(item.entered_at) }}</div>
                    <div>置信度：{{ item.confidence_score.toFixed(2) }}</div>
                    <div>原因：{{ item.reason }}</div>
                  </div>
                </template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>

        <a-empty
          v-if="!scalingQuery.isLoading.value && relatedScalingCandidates.length === 0"
          description="暂无扩量候选"
        />
      </a-card>

      <a-card class="section-card" title="清退候选">
        <a-list :data-source="relatedClearanceCandidates" :loading="clearanceQuery.isLoading.value">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>
                  <span class="monospace-text">{{ item.product_variant_id }}</span>
                </template>
                <template #description>
                  <div class="candidate-meta">
                    <div>状态：{{ getSkuLifecycleStateMeta(item.current_state).label }}</div>
                    <div>进入时间：{{ formatDateTime(item.entered_at) }}</div>
                    <div>置信度：{{ item.confidence_score.toFixed(2) }}</div>
                    <div>原因：{{ item.reason }}</div>
                  </div>
                </template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>

        <a-empty
          v-if="!clearanceQuery.isLoading.value && relatedClearanceCandidates.length === 0"
          description="暂无清退候选"
        />
      </a-card>
    </div>
  </div>
</template>

<style scoped>
.page-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card {
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.search-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
}

.two-column-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.candidate-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.monospace-text {
  font-family: monospace;
}

@media (max-width: 992px) {
  .two-column-grid {
    grid-template-columns: 1fr;
  }
}
</style>
