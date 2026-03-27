<script setup lang="ts">
import { ReloadOutlined, StarFilled, TrophyOutlined, LineChartOutlined, CheckOutlined, CloseOutlined, ClockCircleOutlined } from '@ant-design/icons-vue'
import { computed, h, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'

import { formatCurrency, formatDateTime, formatPercent } from '@/adapters/formatters'
import { riskDecisionMeta, sourcePlatformLabel } from '@/adapters/statusMeta'
import {
  useRecommendationsQuery,
  useCandidateRecommendationQuery,
  useRecommendationTrendsQuery,
  useRecommendationsByPlatformQuery,
  useRecommendationFeedbackStatsQuery,
} from '@/queries/useRecommendationsQuery'
import { useCreateFeedbackMutation } from '@/queries/useFeedbackMutation'
import type { RecommendationItem } from '@/types/recommendations'

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
])

const router = useRouter()

const filters = ref({
  min_score: 60,
  category: undefined as string | undefined,
  risk_level: undefined as 'pass' | 'review' | 'reject' | undefined,
  limit: 20,
})

const analyticsParams = ref({
  period: 'day' as 'day' | 'week' | 'month',
  days: 30,
  min_score: 60,
})

const selectedCandidateId = ref<string>()
const showAnalytics = ref(false)

const recommendationsQuery = useRecommendationsQuery(filters)
const candidateRecommendationQuery = useCandidateRecommendationQuery(
  computed(() => selectedCandidateId.value ?? ''),
)
const createFeedbackMutation = useCreateFeedbackMutation()
const trendsQuery = useRecommendationTrendsQuery(analyticsParams)
const platformQuery = useRecommendationsByPlatformQuery(
  computed(() => ({ min_score: analyticsParams.value.min_score })),
)
const feedbackQuery = useRecommendationFeedbackStatsQuery(
  computed(() => ({ days: analyticsParams.value.days })),
)

const recommendations = computed(() => recommendationsQuery.data.value?.items ?? [])
const selectedRecommendation = computed(() => candidateRecommendationQuery.data.value)
const drawerOpen = computed({
  get: () => !!selectedCandidateId.value,
  set: (value: boolean) => {
    if (!value) {
      selectedCandidateId.value = undefined
    }
  },
})

const levelColor = (level: string) => {
  switch (level) {
    case 'HIGH':
      return 'success'
    case 'MEDIUM':
      return 'warning'
    case 'LOW':
      return 'default'
    default:
      return 'default'
  }
}

const levelText = (level: string) => {
  switch (level) {
    case 'HIGH':
      return '强烈推荐'
    case 'MEDIUM':
      return '可以考虑'
    case 'LOW':
      return '不建议'
    default:
      return level
  }
}

const riskTag = (decision?: string | null) =>
  riskDecisionMeta[decision ?? ''] ?? { label: decision ?? '--', color: 'default' }
const sourceLabel = (source?: string) => sourcePlatformLabel[source ?? ''] ?? source ?? '--'
const feedbackActionLabel: Record<string, string> = {
  accepted: '采纳',
  rejected: '拒绝',
  ignored: '忽略',
}

function handleSelectRecommendation(record: RecommendationItem) {
  selectedCandidateId.value = record.candidate_id
}

function handleRefresh() {
  recommendationsQuery.refetch()
  trendsQuery.refetch()
  platformQuery.refetch()
  feedbackQuery.refetch()
}

function handleViewCandidate(candidateId: string) {
  router.push(`/candidates?id=${candidateId}`)
}

async function handleFeedback(action: 'accepted' | 'rejected' | 'deferred', comment?: string) {
  if (!selectedCandidateId.value) return

  try {
    await createFeedbackMutation.mutateAsync({
      candidateId: selectedCandidateId.value,
      payload: { action, comment },
    })
    message.success('反馈已提交')
    drawerOpen.value = false
  } catch (error) {
    message.error('提交反馈失败')
  }
}

const trendChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { top: 0 },
  grid: { left: 32, right: 16, top: 40, bottom: 32, containLabel: true },
  xAxis: {
    type: 'category',
    data: trendsQuery.data.value?.data.map((item) => item.date) ?? [],
  },
  yAxis: [
    {
      type: 'value',
      name: '推荐数量',
      position: 'left',
    },
    {
      type: 'value',
      name: '平均推荐分',
      position: 'right',
      min: 0,
      max: 100,
    },
  ],
  series: [
    {
      name: '推荐数量',
      type: 'bar',
      data: trendsQuery.data.value?.data.map((item) => item.count) ?? [],
      itemStyle: { color: '#1677ff' },
    },
    {
      name: '平均推荐分',
      type: 'line',
      yAxisIndex: 1,
      smooth: true,
      data: trendsQuery.data.value?.data.map((item) => item.average_score) ?? [],
      itemStyle: { color: '#52c41a' },
    },
  ],
}))

const platformChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { top: 0 },
  grid: { left: 32, right: 16, top: 40, bottom: 48, containLabel: true },
  xAxis: {
    type: 'category',
    data: platformQuery.data.value?.data.map((item) => sourceLabel(item.platform)) ?? [],
    axisLabel: { interval: 0, rotate: 20 },
  },
  yAxis: [
    {
      type: 'value',
      name: '推荐数量',
      position: 'left',
    },
    {
      type: 'value',
      name: '平均推荐分',
      position: 'right',
      min: 0,
      max: 100,
    },
  ],
  series: [
    {
      name: '推荐数量',
      type: 'bar',
      data: platformQuery.data.value?.data.map((item) => item.count) ?? [],
      itemStyle: { color: '#722ed1' },
    },
    {
      name: '平均推荐分',
      type: 'line',
      yAxisIndex: 1,
      smooth: true,
      data: platformQuery.data.value?.data.map((item) => item.average_score) ?? [],
      itemStyle: { color: '#fa8c16' },
    },
  ],
}))

const feedbackChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 32, right: 16, top: 24, bottom: 32, containLabel: true },
  xAxis: {
    type: 'category',
    data: feedbackQuery.data.value?.data.map((item) => feedbackActionLabel[item.action] ?? item.action) ?? [],
    axisLabel: { interval: 0 },
  },
  yAxis: { type: 'value', name: '反馈数量' },
  series: [
    {
      type: 'bar',
      data: feedbackQuery.data.value?.data.map((item) => item.count) ?? [],
      itemStyle: { color: '#13c2c2' },
    },
  ],
}))

const columns = [
  {
    title: '推荐等级',
    dataIndex: 'recommendation_level',
    key: 'recommendation_level',
    width: 120,
  },
  {
    title: '推荐分数',
    dataIndex: 'recommendation_score',
    key: 'recommendation_score',
    width: 120,
  },
  {
    title: '产品标题',
    dataIndex: 'title',
    key: 'title',
  },
  {
    title: '品类',
    dataIndex: 'category',
    key: 'category',
    width: 120,
  },
  {
    title: '平台价格',
    dataIndex: 'platform_price',
    key: 'platform_price',
    width: 120,
  },
  {
    title: '利润率',
    dataIndex: 'margin_percentage',
    key: 'margin_percentage',
    width: 100,
  },
  {
    title: '风险',
    dataIndex: 'risk_decision',
    key: 'risk_decision',
    width: 100,
  },
  {
    title: '操作',
    key: 'action',
    width: 100,
  },
]
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="智能推荐">
      <template #extra>
        <a-button :icon="h(ReloadOutlined)" :loading="recommendationsQuery.isFetching.value" @click="handleRefresh">
          刷新
        </a-button>
      </template>

      <div class="page-stack">
        <a-alert
          type="info"
          show-icon
          message="基于优先级、利润率、风险和供应商质量的综合评分，为您推荐最有潜力的候选产品。"
        />

        <a-card size="small" title="推荐分析看板">
          <template #extra>
            <a-button type="link" :icon="h(LineChartOutlined)" @click="showAnalytics = !showAnalytics">
              {{ showAnalytics ? '收起分析' : '展开分析' }}
            </a-button>
          </template>

          <div v-if="showAnalytics" class="page-stack">
            <div class="filter-grid">
              <a-select
                v-model:value="analyticsParams.period"
                :options="[
                  { label: '按日', value: 'day' },
                  { label: '按周', value: 'week' },
                  { label: '按月', value: 'month' },
                ]"
              />
              <a-input-number
                v-model:value="analyticsParams.days"
                :min="1"
                :max="365"
                style="width: 100%"
                addon-before="回溯天数"
              />
              <a-input-number
                v-model:value="analyticsParams.min_score"
                :min="0"
                :max="100"
                style="width: 100%"
                addon-before="最低分数"
              />
            </div>

            <div class="two-column-grid">
              <a-card size="small" title="时间趋势分析">
                <VChart class="chart-container" :option="trendChartOption" autoresize />
              </a-card>
              <a-card size="small" title="平台对比分析">
                <VChart class="chart-container" :option="platformChartOption" autoresize />
              </a-card>
            </div>

            <a-card size="small" title="用户反馈统计">
              <VChart class="chart-container" :option="feedbackChartOption" autoresize />
            </a-card>
          </div>
        </a-card>

        <!-- 筛选器 -->
        <div class="filter-grid">
          <a-input-number
            v-model:value="filters.min_score"
            :min="0"
            :max="100"
            style="width: 100%"
            placeholder="最低推荐分数"
            addon-before="最低分数"
          />
          <a-input
            v-model:value="filters.category"
            placeholder="品类筛选"
            allow-clear
          />
          <a-select
            v-model:value="filters.risk_level"
            placeholder="风险等级"
            allow-clear
            :options="[
              { label: '低风险 (PASS)', value: 'pass' },
              { label: '需审核 (REVIEW)', value: 'review' },
              { label: '高风险 (REJECT)', value: 'reject' },
            ]"
          />
          <a-input-number
            v-model:value="filters.limit"
            :min="1"
            :max="100"
            style="width: 100%"
            placeholder="返回数量"
            addon-before="数量"
          />
        </div>

        <!-- 推荐列表 -->
        <a-table
          :columns="columns"
          :data-source="recommendations"
          :loading="recommendationsQuery.isLoading.value"
          :pagination="false"
          row-key="candidate_id"
          @row-click="handleSelectRecommendation"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'recommendation_level'">
              <a-tag :color="levelColor(record.recommendation_level)">
                <TrophyOutlined v-if="record.recommendation_level === 'HIGH'" />
                {{ levelText(record.recommendation_level) }}
              </a-tag>
            </template>

            <template v-if="column.key === 'recommendation_score'">
              <a-progress
                :percent="record.recommendation_score"
                :stroke-color="record.recommendation_score >= 75 ? '#52c41a' : record.recommendation_score >= 60 ? '#faad14' : '#d9d9d9'"
                :format="(percent: number) => `${percent?.toFixed(1)}分`"
              />
            </template>

            <template v-if="column.key === 'platform_price'">
              {{ formatCurrency(record.platform_price) }}
            </template>

            <template v-if="column.key === 'margin_percentage'">
              <span :style="{ color: (record.margin_percentage ?? 0) >= 35 ? '#52c41a' : '#faad14' }">
                {{ formatPercent(record.margin_percentage) }}
              </span>
            </template>

            <template v-if="column.key === 'risk_decision'">
              <a-tag :color="riskTag(record.risk_decision).color">
                {{ riskTag(record.risk_decision).label }}
              </a-tag>
            </template>

            <template v-if="column.key === 'action'">
              <a-button type="link" size="small" @click.stop="handleViewCandidate(record.candidate_id)">
                查看详情
              </a-button>
            </template>
          </template>
        </a-table>

        <!-- 统计信息 -->
        <a-card v-if="recommendationsQuery.data.value" size="small">
          <a-statistic-group>
            <a-statistic title="推荐产品数" :value="recommendationsQuery.data.value.count" />
            <a-statistic
              title="筛选条件"
              :value="`最低分数: ${filters.min_score}分`"
            />
          </a-statistic-group>
        </a-card>
      </div>
    </a-card>

    <!-- 推荐详情抽屉 -->
    <a-drawer
      v-model:open="drawerOpen"
      title="推荐详情"
      width="720"
      @close="selectedCandidateId = undefined"
    >
      <div v-if="candidateRecommendationQuery.isLoading.value" class="loading-container">
        <a-spin />
      </div>

      <div v-else-if="selectedRecommendation" class="page-stack">
        <!-- 基本信息 -->
        <a-card title="产品信息" size="small">
          <a-descriptions :column="2" size="small">
            <a-descriptions-item label="产品标题">
              {{ selectedRecommendation.title }}
            </a-descriptions-item>
            <a-descriptions-item label="品类">
              {{ selectedRecommendation.category ?? '--' }}
            </a-descriptions-item>
            <a-descriptions-item label="平台">
              {{ sourceLabel(selectedRecommendation.source_platform) }}
            </a-descriptions-item>
            <a-descriptions-item label="平台价格">
              {{ formatCurrency(selectedRecommendation.platform_price) }}
            </a-descriptions-item>
            <a-descriptions-item label="销量">
              {{ selectedRecommendation.sales_count ?? '--' }}
            </a-descriptions-item>
            <a-descriptions-item label="评分">
              <a-rate :value="selectedRecommendation.rating ?? 0" disabled allow-half />
              {{ selectedRecommendation.rating?.toFixed(1) ?? '--' }}
            </a-descriptions-item>
          </a-descriptions>
        </a-card>

        <!-- 推荐评分 -->
        <a-card title="推荐评分" size="small">
          <div class="page-stack">
            <div style="text-align: center">
              <a-progress
                type="circle"
                :percent="selectedRecommendation.recommendation.score"
                :stroke-color="selectedRecommendation.recommendation.score >= 75 ? '#52c41a' : selectedRecommendation.recommendation.score >= 60 ? '#faad14' : '#d9d9d9'"
                :format="(percent: number) => `${percent?.toFixed(1)}分`"
              />
              <div style="margin-top: 16px">
                <a-tag :color="levelColor(selectedRecommendation.recommendation.level)" style="font-size: 16px; padding: 8px 16px">
                  {{ levelText(selectedRecommendation.recommendation.level) }}
                </a-tag>
              </div>
            </div>

            <!-- 分数构成 -->
            <a-card title="分数构成" size="small">
              <div
                v-for="component in selectedRecommendation.recommendation.score_breakdown.components"
                :key="component.name"
                style="margin-bottom: 12px"
              >
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px">
                  <span>{{ component.description }} ({{ component.weight }})</span>
                  <span style="font-weight: bold">{{ component.value.toFixed(2) }}分</span>
                </div>
                <a-progress
                  :percent="(component.value / parseFloat(component.weight)) * 100"
                  :show-info="false"
                  stroke-color="#1890ff"
                />
              </div>
            </a-card>

            <!-- 推荐理由 -->
            <a-card title="推荐理由" size="small">
              <a-list :data-source="selectedRecommendation.recommendation.reasons" size="small">
                <template #renderItem="{ item }">
                  <a-list-item>
                    <StarFilled style="color: #faad14; margin-right: 8px" />
                    {{ item }}
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </div>
        </a-card>

        <!-- 定价摘要 -->
        <a-card v-if="selectedRecommendation.pricing_summary" title="定价摘要" size="small">
          <a-descriptions :column="2" size="small">
            <a-descriptions-item label="利润率">
              <span :style="{ color: (selectedRecommendation.pricing_summary.margin_percentage ?? 0) >= 35 ? '#52c41a' : '#faad14' }">
                {{ formatPercent(selectedRecommendation.pricing_summary.margin_percentage) }}
              </span>
            </a-descriptions-item>
            <a-descriptions-item label="盈利性">
              <a-tag :color="selectedRecommendation.pricing_summary.profitability_decision === 'profitable' ? 'success' : 'warning'">
                {{ selectedRecommendation.pricing_summary.profitability_decision }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="建议价格">
              {{ formatCurrency(selectedRecommendation.pricing_summary.recommended_price) }}
            </a-descriptions-item>
          </a-descriptions>
        </a-card>

        <!-- 风险摘要 -->
        <a-card v-if="selectedRecommendation.risk_summary" title="风险摘要" size="small">
          <a-descriptions :column="2" size="small">
            <a-descriptions-item label="风险分数">
              {{ selectedRecommendation.risk_summary.score }}
            </a-descriptions-item>
            <a-descriptions-item label="风险决策">
              <a-tag :color="riskTag(selectedRecommendation.risk_summary.decision).color">
                {{ riskTag(selectedRecommendation.risk_summary.decision).label }}
              </a-tag>
            </a-descriptions-item>
          </a-descriptions>
        </a-card>

        <!-- 最佳供应商 -->
        <a-card v-if="selectedRecommendation.best_supplier" title="最佳供应商" size="small">
          <a-descriptions :column="2" size="small">
            <a-descriptions-item label="供应商">
              {{ selectedRecommendation.best_supplier.supplier_name }}
            </a-descriptions-item>
            <a-descriptions-item label="供应价">
              {{ formatCurrency(selectedRecommendation.best_supplier.supplier_price) }}
            </a-descriptions-item>
            <a-descriptions-item label="置信度">
              {{ formatPercent(selectedRecommendation.best_supplier.confidence_score ? selectedRecommendation.best_supplier.confidence_score * 100 : null) }}
            </a-descriptions-item>
            <a-descriptions-item label="MOQ">
              {{ selectedRecommendation.best_supplier.moq ?? '--' }}
            </a-descriptions-item>
          </a-descriptions>
        </a-card>

        <!-- 用户反馈 -->
        <a-card title="您的决策" size="small">
          <div style="display: flex; gap: 12px; flex-wrap: wrap">
            <a-button
              type="primary"
              :icon="h(CheckOutlined)"
              :loading="createFeedbackMutation.isPending.value"
              @click="handleFeedback('accepted')"
            >
              接受推荐
            </a-button>
            <a-button
              danger
              :icon="h(CloseOutlined)"
              :loading="createFeedbackMutation.isPending.value"
              @click="handleFeedback('rejected')"
            >
              拒绝推荐
            </a-button>
            <a-button
              :icon="h(ClockCircleOutlined)"
              :loading="createFeedbackMutation.isPending.value"
              @click="handleFeedback('deferred')"
            >
              稍后决策
            </a-button>
          </div>
        </a-card>
      </div>
    </a-drawer>
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

.filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.two-column-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.chart-container {
  width: 100%;
  min-height: 320px;
}

.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
</style>
