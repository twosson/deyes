<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'

import { assetTypeLabel, candidateStatusMeta, lifecycleMeta, listingStatusMeta } from '@/adapters/statusMeta'
import { useAssetTypeDistributionQuery } from '@/queries/useContentAssetsQuery'
import { useListingStatusDistributionQuery } from '@/queries/usePlatformListingsQuery'
import { useProductStatsQuery } from '@/queries/useProductsQuery'
import { useRecommendationStatsOverviewQuery } from '@/queries/useRecommendationsQuery'

use([
  CanvasRenderer,
  PieChart,
  BarChart,
  ScatterChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
])

const productStatsQuery = useProductStatsQuery()
const assetDistQuery = useAssetTypeDistributionQuery()
const listingDistQuery = useListingStatusDistributionQuery()
const recommendationStatsQuery = useRecommendationStatsOverviewQuery()

const stats = computed(() => productStatsQuery.data.value)
const recStats = computed(() => recommendationStatsQuery.data.value)

const lifecycleData = computed(() =>
  Object.entries(stats.value?.by_lifecycle ?? {}).map(([key, value]) => ({
    name: lifecycleMeta[key]?.label ?? key,
    value,
  }))
)

const candidateStatusData = computed(() =>
  Object.entries(stats.value?.by_status ?? {}).map(([key, value]) => ({
    name: candidateStatusMeta[key]?.label ?? key,
    value,
  }))
)

const assetTypeData = computed(() =>
  Object.entries(assetDistQuery.data.value ?? {}).map(([key, value]) => ({
    name: assetTypeLabel[key] ?? key,
    value,
  }))
)

const listingStatusData = computed(() =>
  Object.entries(listingDistQuery.data.value ?? {}).map(([key, value]) => ({
    name: listingStatusMeta[key]?.label ?? key,
    value,
  }))
)

const lifecycleOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      data: lifecycleData.value,
    },
  ],
}))

const candidateStatusOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [
    {
      type: 'pie',
      radius: '65%',
      data: candidateStatusData.value,
    },
  ],
}))

const assetTypeOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 32, right: 16, top: 24, bottom: 32, containLabel: true },
  xAxis: {
    type: 'category',
    data: assetTypeData.value.map((item) => item.name),
    axisLabel: { interval: 0, rotate: 20 },
  },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'bar',
      data: assetTypeData.value.map((item) => item.value),
      itemStyle: { color: '#1677ff' },
    },
  ],
}))

const listingStatusOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 32, right: 16, top: 24, bottom: 32, containLabel: true },
  xAxis: {
    type: 'category',
    data: listingStatusData.value.map((item) => item.name),
    axisLabel: { interval: 0, rotate: 20 },
  },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'bar',
      data: listingStatusData.value.map((item) => item.value),
      itemStyle: { color: '#13c2c2' },
    },
  ],
}))

// Recommendation analytics
const levelLabels: Record<string, string> = {
  HIGH: '高推荐',
  MEDIUM: '中推荐',
  LOW: '低推荐',
}

const recommendationLevelData = computed(() =>
  Object.entries(recStats.value?.by_level ?? {}).map(([key, value]) => ({
    name: levelLabels[key] ?? key,
    value,
  }))
)

const recommendationCategoryData = computed(() =>
  Object.entries(recStats.value?.by_category ?? {}).map(([key, value]) => ({
    name: key || '未分类',
    value,
  }))
)

const scoreDistributionData = computed(() =>
  (recStats.value?.score_distribution ?? []).map((item) => ({
    name: item.range,
    value: item.count,
  }))
)

const marginVsScoreData = computed(() => {
  const data = recStats.value?.margin_vs_score ?? []
  return data.slice(0, 100).map((item) => [item.margin, item.score, item.category])
})

const recommendationLevelOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      data: recommendationLevelData.value,
    },
  ],
}))

const recommendationCategoryOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 32, right: 16, top: 24, bottom: 32, containLabel: true },
  xAxis: {
    type: 'category',
    data: recommendationCategoryData.value.map((item) => item.name),
    axisLabel: { interval: 0, rotate: 20 },
  },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'bar',
      data: recommendationCategoryData.value.map((item) => item.value),
      itemStyle: { color: '#52c41a' },
    },
  ],
}))

const scoreDistributionOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 32, right: 16, top: 24, bottom: 32, containLabel: true },
  xAxis: {
    type: 'category',
    data: scoreDistributionData.value.map((item) => item.name),
  },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'bar',
      data: scoreDistributionData.value.map((item) => item.value),
      itemStyle: { color: '#faad14' },
    },
  ],
}))

const marginVsScoreOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: (params: any) => {
      const [margin, score, category] = params.value
      return `利润率: ${margin.toFixed(1)}%<br/>推荐分: ${score.toFixed(1)}<br/>品类: ${category || '未分类'}`
    },
  },
  grid: { left: 48, right: 16, top: 24, bottom: 32, containLabel: true },
  xAxis: {
    type: 'value',
    name: '利润率 (%)',
    nameLocation: 'middle',
    nameGap: 30,
  },
  yAxis: {
    type: 'value',
    name: '推荐分',
    nameLocation: 'middle',
    nameGap: 40,
  },
  series: [
    {
      type: 'scatter',
      data: marginVsScoreData.value,
      symbolSize: 8,
      itemStyle: {
        color: '#1677ff',
      },
    },
  ],
}))
</script>

<template>
  <div class="page-stack">
    <a-tabs default-active-key="products">
      <a-tab-pane key="products" tab="商品分析">
        <div class="kpi-grid">
          <a-card class="metric-card" title="商品总量">
            <div class="metric-value">{{ stats?.total_products ?? 0 }}</div>
            <div class="muted-text">生命周期口径统计</div>
          </a-card>
          <a-card class="metric-card" title="内容资产总量">
            <div class="metric-value">{{ stats?.total_assets ?? 0 }}</div>
            <div class="muted-text">累计生成素材数</div>
          </a-card>
          <a-card class="metric-card" title="发布总量">
            <div class="metric-value">{{ stats?.total_listings ?? 0 }}</div>
            <div class="muted-text">累计创建 listing 数</div>
          </a-card>
          <a-card class="metric-card" title="已发布商品">
            <div class="metric-value">{{ stats?.total_published ?? 0 }}</div>
            <div class="muted-text">生命周期为 published</div>
          </a-card>
        </div>

        <div class="two-column-grid">
          <a-card class="section-card" title="商品生命周期分布">
            <VChart class="chart-container" :option="lifecycleOption" autoresize />
          </a-card>
          <a-card class="section-card" title="候选状态分布">
            <VChart class="chart-container" :option="candidateStatusOption" autoresize />
          </a-card>
        </div>

        <div class="two-column-grid">
          <a-card class="section-card" title="素材类型分布">
            <VChart class="chart-container" :option="assetTypeOption" autoresize />
          </a-card>
          <a-card class="section-card" title="Listing 状态分布">
            <VChart class="chart-container" :option="listingStatusOption" autoresize />
          </a-card>
        </div>
      </a-tab-pane>

      <a-tab-pane key="recommendations" tab="推荐分析">
        <div class="kpi-grid">
          <a-card class="metric-card" title="推荐总数">
            <div class="metric-value">{{ recStats?.total_recommendations ?? 0 }}</div>
            <div class="muted-text">推荐分数 ≥ 60 的候选数</div>
          </a-card>
          <a-card class="metric-card" title="平均推荐分">
            <div class="metric-value">{{ recStats?.average_score?.toFixed?.(1) ?? '0.0' }}</div>
            <div class="muted-text">当前推荐池平均得分</div>
          </a-card>
          <a-card class="metric-card" title="高分推荐数">
            <div class="metric-value">{{ recStats?.high_quality_count ?? 0 }}</div>
            <div class="muted-text">推荐分数 ≥ 75</div>
          </a-card>
          <a-card class="metric-card" title="高分占比">
            <div class="metric-value">{{ recStats?.high_quality_percentage?.toFixed?.(1) ?? '0.0' }}%</div>
            <div class="muted-text">高分推荐在推荐池中的占比</div>
          </a-card>
        </div>

        <div class="two-column-grid">
          <a-card class="section-card" title="推荐等级分布">
            <VChart class="chart-container" :option="recommendationLevelOption" autoresize />
          </a-card>
          <a-card class="section-card" title="品类分布">
            <VChart class="chart-container" :option="recommendationCategoryOption" autoresize />
          </a-card>
        </div>

        <div class="two-column-grid">
          <a-card class="section-card" title="推荐分分布">
            <VChart class="chart-container" :option="scoreDistributionOption" autoresize />
          </a-card>
          <a-card class="section-card" title="利润率 vs 推荐分">
            <VChart class="chart-container" :option="marginVsScoreOption" autoresize />
          </a-card>
        </div>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>
