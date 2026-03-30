<script setup lang="ts">
import { ReloadOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'

import { formatNumber } from '@/adapters/formatters'
import { anomalySeverityMeta } from '@/adapters/statusMeta'
import { useOperationsSummaryQuery } from '@/queries/useOperationsQuery'

use([CanvasRenderer, PieChart, TitleComponent, TooltipComponent, LegendComponent])

const summaryQuery = useOperationsSummaryQuery()

const summary = computed(() => summaryQuery.data.value)

const severityData = computed(() =>
  Object.entries(summary.value?.daily_exceptions?.by_severity ?? {}).map(([key, value]) => ({
    name: anomalySeverityMeta[key]?.label ?? key,
    value,
  }))
)

const severityOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      data: severityData.value,
    },
  ],
}))
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="运营控制台">
      <template #extra>
        <a-button :loading="summaryQuery.isFetching.value" @click="summaryQuery.refetch()">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </template>

      <a-alert
        type="info"
        show-icon
        message="运营控制台汇总视图，展示今日异常、扩量候选、清退候选和待审批动作的统计数据。"
      />
    </a-card>

    <div class="kpi-grid">
      <a-card class="metric-card" title="今日异常总数">
        <div class="metric-value">{{ formatNumber(summary?.daily_exceptions?.total ?? null) }}</div>
        <div class="muted-text">今日检测到的异常数量</div>
      </a-card>
      <a-card class="metric-card" title="扩量候选">
        <div class="metric-value">{{ formatNumber(summary?.scaling_candidates_count ?? null) }}</div>
        <div class="muted-text">值得加码的 SKU 数量</div>
      </a-card>
      <a-card class="metric-card" title="清退候选">
        <div class="metric-value">{{ formatNumber(summary?.clearance_candidates_count ?? null) }}</div>
        <div class="muted-text">应清退的 SKU 数量</div>
      </a-card>
      <a-card class="metric-card" title="待审批动作">
        <div class="metric-value">{{ formatNumber(summary?.pending_actions_count ?? null) }}</div>
        <div class="muted-text">等待人工审批的动作数</div>
      </a-card>
    </div>

    <a-card class="section-card" title="异常严重程度分布">
      <VChart class="chart-container" :option="severityOption" autoresize />
    </a-card>

    <a-card class="section-card" title="快捷操作">
      <div class="quick-actions">
        <router-link to="/operations/exceptions">
          <a-button type="primary" size="large">查看今日异常</a-button>
        </router-link>
        <router-link to="/operations/pending-actions">
          <a-button type="primary" size="large">查看待审批动作</a-button>
        </router-link>
        <router-link to="/operations/lifecycle">
          <a-button type="primary" size="large">SKU 生命周期追踪</a-button>
        </router-link>
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
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.metric-card {
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.metric-value {
  font-size: 32px;
  font-weight: 600;
  color: #1677ff;
  margin: 8px 0;
}

.muted-text {
  color: rgba(0, 0, 0, 0.45);
  font-size: 14px;
}

.chart-container {
  height: 400px;
  width: 100%;
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}
</style>
