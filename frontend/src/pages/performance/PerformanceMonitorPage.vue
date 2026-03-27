<script setup lang="ts">
import { ReloadOutlined } from '@ant-design/icons-vue'
import { computed, h, ref } from 'vue'

import { formatCurrency, formatDateTime, formatNumber, formatPercent } from '@/adapters/formatters'
import {
  useDashboardAssetsQuery,
  useDashboardListingsQuery,
  usePerformanceOverviewQuery,
  useRecentAutoActionsQuery,
} from '@/queries/usePerformanceQuery'

const listingLimit = ref(20)
const assetLimit = ref(20)
const actionLimit = ref(20)

const overviewQuery = usePerformanceOverviewQuery()
const listingsQuery = useDashboardListingsQuery(listingLimit)
const assetsQuery = useDashboardAssetsQuery(assetLimit)
const actionsQuery = useRecentAutoActionsQuery(actionLimit)

const overview = computed(() => overviewQuery.data.value)
const listings = computed(() => listingsQuery.data.value?.items ?? [])
const assets = computed(() => assetsQuery.data.value?.items ?? [])
const actions = computed(() => actionsQuery.data.value?.items ?? [])

const listingColumns = [
  { title: '平台', dataIndex: 'platform', key: 'platform', width: 120 },
  { title: '区域', dataIndex: 'region', key: 'region', width: 100 },
  { title: '平台商品ID', dataIndex: 'platform_listing_id', key: 'platform_listing_id', ellipsis: true },
  { title: '价格', dataIndex: 'price', key: 'price', width: 110 },
  { title: '曝光', dataIndex: 'impressions', key: 'impressions', width: 100 },
  { title: '点击', dataIndex: 'clicks', key: 'clicks', width: 100 },
  { title: '订单', dataIndex: 'orders', key: 'orders', width: 100 },
  { title: '营收', dataIndex: 'revenue', key: 'revenue', width: 120 },
  { title: '广告花费', dataIndex: 'ad_spend', key: 'ad_spend', width: 120 },
  { title: 'CTR', dataIndex: 'ctr', key: 'ctr', width: 100 },
  { title: 'CVR', dataIndex: 'cvr', key: 'cvr', width: 100 },
  { title: 'ROI', dataIndex: 'roi', key: 'roi', width: 100 },
  { title: 'ROAS', dataIndex: 'roas', key: 'roas', width: 100 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
]

const assetColumns = [
  { title: '素材类型', dataIndex: 'asset_type', key: 'asset_type', width: 120 },
  { title: '素材链接', dataIndex: 'file_url', key: 'file_url', ellipsis: true },
  { title: 'AI质量分', dataIndex: 'ai_quality_score', key: 'ai_quality_score', width: 110 },
  { title: '曝光', dataIndex: 'impressions', key: 'impressions', width: 100 },
  { title: '点击', dataIndex: 'clicks', key: 'clicks', width: 100 },
  { title: '订单', dataIndex: 'orders', key: 'orders', width: 100 },
  { title: '营收', dataIndex: 'revenue', key: 'revenue', width: 120 },
  { title: 'CTR', dataIndex: 'ctr', key: 'ctr', width: 100 },
  { title: 'CVR', dataIndex: 'cvr', key: 'cvr', width: 100 },
]

const actionColumns = [
  { title: '事件类型', dataIndex: 'event_type', key: 'event_type', width: 180 },
  { title: 'Listing ID', dataIndex: 'listing_id', key: 'listing_id', ellipsis: true },
  { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '详情', dataIndex: 'payload', key: 'payload' },
]

function handleRefresh() {
  void overviewQuery.refetch()
  void listingsQuery.refetch()
  void assetsQuery.refetch()
  void actionsQuery.refetch()
}

function formatActionType(eventType: string) {
  switch (eventType) {
    case 'auto_reprice':
      return '自动调价'
    case 'auto_pause':
      return '自动暂停'
    case 'auto_asset_switch':
      return '自动切换素材'
    case 'auto_reprice_failed':
      return '自动调价失败'
    case 'auto_pause_failed':
      return '自动暂停失败'
    case 'auto_asset_switch_failed':
      return '自动切换素材失败'
    default:
      return eventType
  }
}

function formatActionPayload(payload: Record<string, unknown>) {
  const pairs = Object.entries(payload)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${String(value)}`)

  return pairs.length > 0 ? pairs.join(' | ') : '--'
}
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="性能监控">
      <template #extra>
        <a-button :icon="h(ReloadOutlined)" :loading="overviewQuery.isFetching.value || listingsQuery.isFetching.value || assetsQuery.isFetching.value || actionsQuery.isFetching.value" @click="handleRefresh">
          刷新
        </a-button>
      </template>

      <div class="page-stack">
        <a-alert
          type="info"
          show-icon
          message="展示最近 7 天的 listing、素材和自动化动作数据，为自动优化引擎提供可视化反馈闭环。"
        />

        <div class="kpi-grid">
          <a-card class="metric-card" title="活跃 Listing">
            <div class="metric-value">{{ formatNumber(overview?.active_listings_count ?? null) }}</div>
            <div class="muted-text">状态为 active 或 paused 的 listing 数</div>
          </a-card>
          <a-card class="metric-card" title="已跟踪 Listing">
            <div class="metric-value">{{ formatNumber(overview?.tracked_listings_count ?? null) }}</div>
            <div class="muted-text">最近 7 天有性能数据的 listing 数</div>
          </a-card>
          <a-card class="metric-card" title="低 ROI 告警">
            <div class="metric-value">{{ formatNumber(overview?.low_roi_alerts ?? null) }}</div>
            <div class="muted-text">最近 7 天 ROI 低于阈值的 listing</div>
          </a-card>
          <a-card class="metric-card" title="低 CTR 告警">
            <div class="metric-value">{{ formatNumber(overview?.low_ctr_alerts ?? null) }}</div>
            <div class="muted-text">最近 7 天 CTR 低于阈值的素材</div>
          </a-card>
        </div>

        <a-card size="small" title="Listing 表现排行（最近 7 天）">
          <template #extra>
            <a-input-number v-model:value="listingLimit" :min="1" :max="100" addon-before="数量" style="width: 140px" />
          </template>
          <a-table
            :columns="listingColumns"
            :data-source="listings"
            :loading="listingsQuery.isLoading.value"
            :pagination="false"
            :scroll="{ x: 1500 }"
            row-key="listing_id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'price'">
                {{ formatCurrency(record.price, record.currency) }}
              </template>
              <template v-else-if="column.key === 'impressions' || column.key === 'clicks' || column.key === 'orders'">
                {{ formatNumber(record[column.key]) }}
              </template>
              <template v-else-if="column.key === 'revenue' || column.key === 'ad_spend'">
                {{ formatCurrency(record[column.key], record.currency) }}
              </template>
              <template v-else-if="column.key === 'ctr' || column.key === 'cvr' || column.key === 'roi'">
                <span :style="{ color: column.key === 'roi' && record.roi < 10 ? '#ff4d4f' : undefined }">
                  {{ formatPercent(record[column.key]) }}
                </span>
              </template>
              <template v-else-if="column.key === 'roas'">
                {{ Number(record.roas ?? 0).toFixed(2) }}
              </template>
              <template v-else-if="column.key === 'status'">
                <a-tag :color="record.status === 'active' ? 'success' : record.status === 'paused' ? 'warning' : 'default'">
                  {{ record.status }}
                </a-tag>
              </template>
            </template>
          </a-table>
        </a-card>

        <div class="two-column-grid">
          <a-card size="small" title="素材 CTR 排行（最近 7 天）">
            <template #extra>
              <a-input-number v-model:value="assetLimit" :min="1" :max="100" addon-before="数量" style="width: 140px" />
            </template>
            <a-table
              :columns="assetColumns"
              :data-source="assets"
              :loading="assetsQuery.isLoading.value"
              :pagination="false"
              :scroll="{ x: 980 }"
              row-key="asset_id"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'file_url'">
                  <a :href="record.file_url" target="_blank" rel="noreferrer">
                    {{ record.file_url }}
                  </a>
                </template>
                <template v-else-if="column.key === 'ai_quality_score'">
                  {{ record.ai_quality_score?.toFixed?.(1) ?? '--' }}
                </template>
                <template v-else-if="column.key === 'impressions' || column.key === 'clicks' || column.key === 'orders'">
                  {{ formatNumber(record[column.key]) }}
                </template>
                <template v-else-if="column.key === 'revenue'">
                  {{ formatCurrency(record.revenue) }}
                </template>
                <template v-else-if="column.key === 'ctr' || column.key === 'cvr'">
                  {{ formatPercent(record[column.key]) }}
                </template>
              </template>
            </a-table>
          </a-card>

          <a-card size="small" title="自动化动作历史">
            <template #extra>
              <a-input-number v-model:value="actionLimit" :min="1" :max="100" addon-before="数量" style="width: 140px" />
            </template>
            <a-table
              :columns="actionColumns"
              :data-source="actions"
              :loading="actionsQuery.isLoading.value"
              :pagination="false"
              :scroll="{ x: 1000 }"
              row-key="event_id"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'event_type'">
                  <a-tag :color="record.event_type.includes('failed') ? 'error' : 'processing'">
                    {{ formatActionType(record.event_type) }}
                  </a-tag>
                </template>
                <template v-else-if="column.key === 'created_at'">
                  {{ formatDateTime(record.created_at) }}
                </template>
                <template v-else-if="column.key === 'payload'">
                  <span class="payload-text">{{ formatActionPayload(record.payload) }}</span>
                </template>
              </template>
            </a-table>
          </a-card>
        </div>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.page-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card {
  width: 100%;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.metric-card {
  height: 100%;
}

.metric-value {
  font-size: 28px;
  font-weight: 600;
  line-height: 1.2;
}

.muted-text {
  margin-top: 8px;
  color: rgba(0, 0, 0, 0.45);
}

.two-column-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 16px;
}

.payload-text {
  color: rgba(0, 0, 0, 0.65);
}
</style>