<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart } from 'echarts/charts'
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

use([CanvasRenderer, PieChart, BarChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent])

const productStatsQuery = useProductStatsQuery()
const assetDistQuery = useAssetTypeDistributionQuery()
const listingDistQuery = useListingStatusDistributionQuery()

const stats = computed(() => productStatsQuery.data.value)

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
</script>

<template>
  <div class="page-stack">
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
  </div>
</template>
