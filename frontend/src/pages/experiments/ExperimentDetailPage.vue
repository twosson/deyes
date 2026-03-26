<script setup lang="ts">
import { TrophyOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'

import { formatDateTime } from '@/adapters/formatters'
import {
  useExperimentDetailQuery,
  useExperimentSummaryQuery,
  usePromoteWinnerMutation,
  useSelectWinnerMutation,
} from '@/queries/useExperimentsQuery'
import { useContentAssetsQuery } from '@/queries/useContentAssetsQuery'
import { ExperimentStatus } from '@/types/experiments'
import type { VariantPerformance } from '@/types/experiments'

use([CanvasRenderer, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent])

const route = useRoute()
const router = useRouter()

const experimentId = computed(() => String(route.params.id ?? ''))

const experimentQuery = useExperimentDetailQuery(experimentId)
const summaryQuery = useExperimentSummaryQuery(experimentId)
const selectWinnerMutation = useSelectWinnerMutation()
const promoteWinnerMutation = usePromoteWinnerMutation()

const experiment = computed(() => experimentQuery.data.value)
const summary = computed(() => summaryQuery.data.value)

// Query assets for the experiment's product
const assetsQuery = useContentAssetsQuery(
  computed(() => ({
    candidate_product_id: experiment.value?.candidate_product_id,
  }))
)

const assets = computed(() => assetsQuery.data.value?.assets ?? [])

const statusColorMap: Record<string, string> = {
  [ExperimentStatus.DRAFT]: 'blue',
  [ExperimentStatus.ACTIVE]: 'green',
  [ExperimentStatus.COMPLETED]: 'purple',
  [ExperimentStatus.ARCHIVED]: 'default',
}

const statusLabelMap: Record<string, string> = {
  [ExperimentStatus.DRAFT]: '草稿',
  [ExperimentStatus.ACTIVE]: '进行中',
  [ExperimentStatus.COMPLETED]: '已完成',
  [ExperimentStatus.ARCHIVED]: '已归档',
}

function getStatusColor(status?: string) {
  return statusColorMap[status ?? ''] ?? 'default'
}

function getStatusLabel(status?: string) {
  return statusLabelMap[status ?? ''] ?? status ?? '--'
}

function isWinner(variant: VariantPerformance) {
  return variant.variant_group === summary.value?.winner_variant_group
}

function getVariantAssets(variantGroup: string) {
  return assets.value.filter((asset) => asset.variant_group === variantGroup)
}

async function handleSelectWinner() {
  await selectWinnerMutation.mutateAsync(experimentId.value)
}

async function handlePromoteWinner() {
  await promoteWinnerMutation.mutateAsync(experimentId.value)
}

function goBack() {
  void router.push('/experiments')
}

// Chart option for performance trends
const chartOption = computed(() => {
  const variants = summary.value?.variants ?? []

  return {
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: variants.map((v) => `变体 ${v.variant_group}`),
      bottom: 0,
    },
    grid: {
      left: 32,
      right: 16,
      top: 24,
      bottom: 48,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: ['CTR', 'CVR', '订单数', '收入'],
    },
    yAxis: {
      type: 'value',
    },
    series: variants.map((variant) => ({
      name: `变体 ${variant.variant_group}`,
      type: 'line',
      data: [
        variant.ctr,
        variant.cvr,
        variant.orders,
        variant.revenue / 1000, // Scale revenue for better visualization
      ],
    })),
  }
})
</script>

<template>
  <div class="page-stack">
    <a-page-header :title="experiment?.name ?? '实验详情'" @back="goBack">
      <template #tags>
        <a-tag :color="getStatusColor(experiment?.status)">
          {{ getStatusLabel(experiment?.status) }}
        </a-tag>
      </template>
      <template #extra>
        <a-space>
          <a-button
            v-if="experiment?.status === ExperimentStatus.ACTIVE && !experiment?.winner_variant_group"
            :loading="selectWinnerMutation.isPending.value"
            @click="handleSelectWinner"
          >
            自动选择获胜者
          </a-button>
          <a-button
            v-if="experiment?.winner_variant_group"
            type="primary"
            :loading="promoteWinnerMutation.isPending.value"
            @click="handlePromoteWinner"
          >
            提升获胜变体
          </a-button>
        </a-space>
      </template>

      <a-descriptions size="small" :column="3">
        <a-descriptions-item label="目标指标">{{ experiment?.metric_goal ?? '--' }}</a-descriptions-item>
        <a-descriptions-item label="平台">{{ experiment?.target_platform ?? '--' }}</a-descriptions-item>
        <a-descriptions-item label="区域">{{ experiment?.region ?? '--' }}</a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ formatDateTime(experiment?.created_at) }}</a-descriptions-item>
        <a-descriptions-item label="更新时间">{{ formatDateTime(experiment?.updated_at) }}</a-descriptions-item>
      </a-descriptions>
    </a-page-header>

    <!-- Performance Summary Cards -->
    <a-row :gutter="16" class="mb-4">
      <a-col
        v-for="variant in summary?.variants"
        :key="variant.variant_group"
        :xs="24"
        :sm="12"
        :lg="6"
      >
        <a-card>
          <a-statistic
            :title="`变体 ${variant.variant_group}`"
            :value="variant.ctr"
            suffix="%"
            :value-style="{ color: isWinner(variant) ? '#3f8600' : undefined }"
          >
            <template #prefix>
              <TrophyOutlined v-if="isWinner(variant)" />
            </template>
          </a-statistic>
          <div class="mt-2">
            <div>点击数: {{ variant.clicks }}</div>
            <div>曝光数: {{ variant.impressions }}</div>
            <div>订单数: {{ variant.orders }}</div>
            <div>收入: ¥{{ variant.revenue.toFixed(2) }}</div>
          </div>
        </a-card>
      </a-col>
    </a-row>

    <!-- Performance Charts -->
    <a-card title="性能趋势" class="section-card">
      <VChart :option="chartOption" style="height: 400px" autoresize />
    </a-card>

    <!-- Variant Assets -->
    <a-card title="变体素材" class="section-card">
      <a-tabs v-if="summary?.variants && summary.variants.length > 0">
        <a-tab-pane
          v-for="variant in summary.variants"
          :key="variant.variant_group"
          :tab="`变体 ${variant.variant_group}`"
        >
          <a-row :gutter="16">
            <a-col
              v-for="asset in getVariantAssets(variant.variant_group)"
              :key="asset.id"
              :xs="24"
              :sm="12"
              :lg="6"
            >
              <a-card hoverable>
                <template #cover>
                  <div style="height: 200px; overflow: hidden">
                    <img
                      :src="asset.file_url"
                      :alt="asset.asset_type"
                      style="width: 100%; height: 100%; object-fit: cover"
                    />
                  </div>
                </template>
                <a-card-meta :title="asset.asset_type">
                  <template #description>
                    <div>质量分: {{ asset.ai_quality_score ?? '--' }}</div>
                    <div>使用次数: {{ asset.usage_count }}</div>
                  </template>
                </a-card-meta>
              </a-card>
            </a-col>
          </a-row>
          <a-empty v-if="getVariantAssets(variant.variant_group).length === 0" description="暂无素材" />
        </a-tab-pane>
      </a-tabs>
      <a-empty v-else description="暂无变体数据" />
    </a-card>
  </div>
</template>
