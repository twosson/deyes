<script setup lang="ts">
import { ReloadOutlined } from '@ant-design/icons-vue'
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'

import { formatDateTime } from '@/adapters/formatters'
import { getAnomalySeverityMeta } from '@/adapters/statusMeta'
import AnomalyCard from '@/components/AnomalyCard.vue'
import { useExceptionsQuery } from '@/queries/useOperationsQuery'
import type { Anomaly } from '@/types/operations'

const filters = ref({
  platform: undefined as string | undefined,
  region: undefined as string | undefined,
})

const exceptionsQuery = useExceptionsQuery(filters)

const exceptions = computed(() => exceptionsQuery.data.value?.anomalies ?? [])
const totalAnomalies = computed(() => exceptionsQuery.data.value?.total_anomalies ?? 0)
const bySeverity = computed(() => exceptionsQuery.data.value?.by_severity ?? { critical: 0, high: 0, medium: 0, low: 0 })

const selectedAnomaly = ref<Anomaly>()
const detailModalOpen = ref(false)

function handleViewDetails(anomaly: Anomaly) {
  selectedAnomaly.value = anomaly
  detailModalOpen.value = true
}

function handleFilter() {
  exceptionsQuery.refetch()
}

function handleReset() {
  filters.value.platform = undefined
  filters.value.region = undefined
  exceptionsQuery.refetch()
}

const severityMeta = computed(() =>
  selectedAnomaly.value ? getAnomalySeverityMeta(selectedAnomaly.value.severity) : null
)
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="今日异常列表">
      <template #extra>
        <a-space>
          <a-button :loading="exceptionsQuery.isFetching.value" @click="exceptionsQuery.refetch()">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
        </a-space>
      </template>

      <div class="page-stack">
        <a-alert
          type="warning"
          show-icon
          message="以下是今日检测到的异常情况，按严重程度分类。点击卡片查看详情。"
        />

        <div class="filter-grid">
          <a-input v-model:value="filters.platform" placeholder="平台，如 temu / amazon" allow-clear />
          <a-input v-model:value="filters.region" placeholder="区域，如 US / EU" allow-clear />
          <a-button type="primary" @click="handleFilter">查询</a-button>
          <a-button @click="handleReset">重置</a-button>
        </div>

        <div class="severity-stats">
          <a-statistic
            title="严重"
            :value="bySeverity.critical ?? 0"
            :value-style="{ color: '#cf1322' }"
          />
          <a-statistic title="高" :value="bySeverity.high ?? 0" :value-style="{ color: '#fa541c' }" />
          <a-statistic
            title="中"
            :value="bySeverity.medium ?? 0"
            :value-style="{ color: '#faad14' }"
          />
          <a-statistic title="低" :value="bySeverity.low ?? 0" :value-style="{ color: '#8c8c8c' }" />
          <a-statistic title="总计" :value="totalAnomalies" :value-style="{ color: '#1677ff' }" />
        </div>
      </div>
    </a-card>

    <a-card class="section-card" title="异常详情">
      <a-spin :spinning="exceptionsQuery.isLoading.value">
        <div v-if="exceptions.length > 0" class="anomaly-grid">
          <AnomalyCard
            v-for="(anomaly, index) in exceptions"
            :key="`${anomaly.type}-${anomaly.product_variant_id ?? 'unknown'}-${index}`"
            :anomaly="anomaly"
            @view-details="handleViewDetails"
          />
        </div>
        <a-empty v-else description="暂无异常数据" />
      </a-spin>
    </a-card>

    <!-- 异常详情 Modal -->
    <a-modal
      v-model:open="detailModalOpen"
      title="异常详情"
      :footer="null"
      width="800px"
    >
      <div v-if="selectedAnomaly" class="page-stack">
        <a-descriptions :column="2" size="small" bordered>
          <a-descriptions-item label="严重程度" :span="2">
            <a-tag v-if="severityMeta" :color="severityMeta.color">
              {{ severityMeta.label }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="异常类型" :span="2">
            {{ selectedAnomaly.type }}
          </a-descriptions-item>
          <a-descriptions-item label="产品变体 ID" :span="2">
            {{ selectedAnomaly.product_variant_id ?? '--' }}
          </a-descriptions-item>
        </a-descriptions>

        <a-card v-if="selectedAnomaly.details" title="详细信息" size="small">
          <pre class="context-json">{{ JSON.stringify(selectedAnomaly.details, null, 2) }}</pre>
        </a-card>
      </div>
    </a-modal>
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

.filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.severity-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 16px;
}

.anomaly-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 16px;
}

.context-json {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
}
</style>
