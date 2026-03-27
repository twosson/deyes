<script setup lang="ts">
import { ReloadOutlined, StarFilled, TrophyOutlined } from '@ant-design/icons-vue'
import { computed, h, ref } from 'vue'
import { useRouter } from 'vue-router'

import { formatCurrency, formatDateTime, formatPercent } from '@/adapters/formatters'
import { riskDecisionMeta, sourcePlatformLabel } from '@/adapters/statusMeta'
import { useRecommendationsQuery, useCandidateRecommendationQuery } from '@/queries/useRecommendationsQuery'
import type { RecommendationItem } from '@/types/recommendations'

const router = useRouter()

const filters = ref({
  min_score: 60,
  category: undefined as string | undefined,
  risk_level: undefined as 'pass' | 'review' | 'reject' | undefined,
  limit: 20,
})

const selectedCandidateId = ref<string>()

const recommendationsQuery = useRecommendationsQuery(filters)
const candidateRecommendationQuery = useCandidateRecommendationQuery(
  computed(() => selectedCandidateId.value ?? ''),
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

function handleSelectRecommendation(record: RecommendationItem) {
  selectedCandidateId.value = record.candidate_id
}

function handleRefresh() {
  recommendationsQuery.refetch()
}

function handleViewCandidate(candidateId: string) {
  router.push(`/candidates?id=${candidateId}`)
}

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

.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
</style>
