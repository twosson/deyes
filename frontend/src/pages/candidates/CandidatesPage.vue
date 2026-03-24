<script setup lang="ts">
import { ReloadOutlined } from '@ant-design/icons-vue'
import { computed, ref } from 'vue'

import SupplierMatchesTable from '@/components/SupplierMatchesTable.vue'
import SupplierRankingCard from '@/components/SupplierRankingCard.vue'
import { formatCurrency, formatDateTime, formatNumber, formatPercent } from '@/adapters/formatters'
import { riskDecisionMeta, sourcePlatformLabel } from '@/adapters/statusMeta'
import { useAgentRunResultsQuery, useAgentRunStatusQuery, useCreateAgentRunMutation } from '@/queries/useAgentRunsQuery'
import { useCandidateDetailQuery, useCandidatesQuery } from '@/queries/useCandidatesQuery'
import type { CandidateProduct } from '@/types/candidates'

const selectedCandidateId = ref<string>()
const latestRunId = ref<string>()
const discoveryForm = ref({
  platform: 'alibaba_1688',
  category: '',
  keywords: '',
  region: '',
  price_min: undefined as number | undefined,
  price_max: undefined as number | undefined,
  max_candidates: 10,
})

const candidatesQuery = useCandidatesQuery()
const createRunMutation = useCreateAgentRunMutation()
const runStatusQuery = useAgentRunStatusQuery(latestRunId)
const runResultsQuery = useAgentRunResultsQuery(latestRunId)
const candidateDetailQuery = useCandidateDetailQuery(computed(() => selectedCandidateId.value ?? ''))

const candidateRows = computed(() => candidatesQuery.data.value?.items ?? [])
const runCandidates = computed(() => runResultsQuery.data.value?.candidates ?? [])
const selectedCandidate = computed(() => candidateDetailQuery.data.value)
const selectedSupplierSelection = computed(
  () => selectedCandidate.value?.pricing_assessment?.explanation?.supplier_selection ?? null,
)
const sortedSupplierMatches = computed(() => {
  if (!selectedCandidate.value?.supplier_matches) return []
  const matches = [...selectedCandidate.value.supplier_matches]
  return matches.sort((a, b) => {
    if (a.selected && !b.selected) return -1
    if (!a.selected && b.selected) return 1
    return 0
  })
})

const riskTag = (decision?: string | null) => riskDecisionMeta[decision ?? ''] ?? { label: decision ?? '--', color: 'default' }
const sourceLabel = (source?: string) => sourcePlatformLabel[source ?? ''] ?? source ?? '--'

function handleSelectCandidate(record: CandidateProduct) {
  selectedCandidateId.value = record.id
}

async function handleStartDiscovery() {
  const keywords = discoveryForm.value.keywords
    .split(/[，,\n]/)
    .map((item) => item.trim())
    .filter(Boolean)

  const response = await createRunMutation.mutateAsync({
    platform: discoveryForm.value.platform,
    category: discoveryForm.value.category || null,
    keywords: keywords.length > 0 ? keywords : null,
    region: discoveryForm.value.region || null,
    price_min: discoveryForm.value.price_min ?? null,
    price_max: discoveryForm.value.price_max ?? null,
    max_candidates: discoveryForm.value.max_candidates,
    target_languages: ['en'],
  })

  latestRunId.value = response.run_id
}
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="选品岗位">
      <div class="page-stack">
        <a-alert
          type="info"
          show-icon
          message="通过 1688 选品任务发起候选商品发现，结合利润测算、风险评估和供应商匹配做人工复核。"
        />

        <div class="filter-grid">
          <a-select v-model:value="discoveryForm.platform" :options="[
            { label: '1688', value: 'alibaba_1688' },
          ]" />
          <a-input v-model:value="discoveryForm.category" placeholder="类目，如：手机配件" />
          <a-input v-model:value="discoveryForm.keywords" placeholder="关键词，逗号分隔" />
          <a-input v-model:value="discoveryForm.region" placeholder="目标地区，如：us" />
          <a-input-number v-model:value="discoveryForm.price_min" :min="0" :precision="2" style="width: 100%" placeholder="最低价" />
          <a-input-number v-model:value="discoveryForm.price_max" :min="0" :precision="2" style="width: 100%" placeholder="最高价" />
          <a-input-number v-model:value="discoveryForm.max_candidates" :min="1" :max="50" style="width: 100%" placeholder="候选数" />
          <a-button type="primary" :loading="createRunMutation.isPending.value" @click="handleStartDiscovery">
            发起选品任务
          </a-button>
        </div>
      </div>
    </a-card>

    <a-row :gutter="16">
      <a-col :span="16">
        <a-card class="section-card" title="候选商品池">
          <template #extra>
            <a-space>
              <a-button :loading="candidatesQuery.isFetching.value" @click="candidatesQuery.refetch()">
                <template #icon><ReloadOutlined /></template>
                刷新
              </a-button>
            </a-space>
          </template>

          <a-table
            :data-source="candidateRows"
            :loading="candidatesQuery.isLoading.value"
            :pagination="false"
            row-key="id"
            size="middle"
          >
            <a-table-column title="商品标题" data-index="title" key="title" :width="260" ellipsis />
            <a-table-column title="来源" key="source_platform" :width="100">
              <template #default="{ record }">
                {{ sourceLabel(record.source_platform) }}
              </template>
            </a-table-column>
            <a-table-column title="平台价" key="platform_price" :width="120">
              <template #default="{ record }">
                {{ formatCurrency(record.platform_price) }}
              </template>
            </a-table-column>
            <a-table-column title="预估毛利" key="estimated_margin" :width="120">
              <template #default="{ record }">
                {{ formatCurrency(record.estimated_margin) }}
              </template>
            </a-table-column>
            <a-table-column title="毛利率" key="margin_percentage" :width="100">
              <template #default="{ record }">
                {{ formatPercent(record.margin_percentage) }}
              </template>
            </a-table-column>
            <a-table-column title="风险决策" key="risk_decision" :width="110">
              <template #default="{ record }">
                <a-tag :color="riskTag(record.risk_decision).color">{{ riskTag(record.risk_decision).label }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column title="风险分" key="risk_score" :width="90">
              <template #default="{ record }">
                {{ formatNumber(record.risk_score) }}
              </template>
            </a-table-column>
            <a-table-column title="入池时间" key="created_at" :width="150">
              <template #default="{ record }">
                {{ formatDateTime(record.created_at) }}
              </template>
            </a-table-column>
            <a-table-column title="操作" key="actions" :width="100" fixed="right">
              <template #default="{ record }">
                <a-button type="link" @click="handleSelectCandidate(record)">查看</a-button>
              </template>
            </a-table-column>
          </a-table>
        </a-card>
      </a-col>

      <a-col :span="8">
        <a-card class="section-card" title="任务状态">
          <a-empty v-if="!latestRunId" description="尚未发起新的选品任务" />
          <div v-else class="page-stack">
            <a-descriptions :column="1" size="small" bordered>
              <a-descriptions-item label="任务 ID">{{ latestRunId }}</a-descriptions-item>
              <a-descriptions-item label="状态">{{ runStatusQuery.data.value?.status ?? '--' }}</a-descriptions-item>
              <a-descriptions-item label="当前步骤">{{ runStatusQuery.data.value?.current_step ?? '--' }}</a-descriptions-item>
              <a-descriptions-item label="已发现候选">
                {{ formatNumber(runStatusQuery.data.value?.candidates_discovered ?? null) }}
              </a-descriptions-item>
              <a-descriptions-item label="进度">
                {{ runStatusQuery.data.value?.progress.completed_steps ?? 0 }}/{{ runStatusQuery.data.value?.progress.total_steps ?? 0 }}
              </a-descriptions-item>
            </a-descriptions>

            <a-card size="small" title="本次任务候选结果">
              <a-list :data-source="runCandidates" size="small">
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-list-item-meta :title="item.title" :description="`毛利率 ${formatPercent(item.margin_percentage)} / 风险 ${item.risk_decision ?? '--'}`" />
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-card class="section-card" title="候选详情">
      <a-empty v-if="!selectedCandidateId" description="从候选商品池选择一个商品查看详情" />
      <div v-else class="page-stack">
        <a-skeleton v-if="candidateDetailQuery.isLoading.value" active />
        <template v-else-if="selectedCandidate">
          <a-row :gutter="16">
            <a-col :span="8">
              <a-image v-if="selectedCandidate.main_image_url" :src="selectedCandidate.main_image_url" width="100%" />
              <a-empty v-else description="暂无主图" />
            </a-col>
            <a-col :span="16">
              <a-descriptions :column="2" bordered size="small">
                <a-descriptions-item label="标题" :span="2">{{ selectedCandidate.title }}</a-descriptions-item>
                <a-descriptions-item label="来源平台">{{ sourceLabel(selectedCandidate.source_platform) }}</a-descriptions-item>
                <a-descriptions-item label="状态">{{ selectedCandidate.status }}</a-descriptions-item>
                <a-descriptions-item label="平台价">{{ formatCurrency(selectedCandidate.platform_price) }}</a-descriptions-item>
                <a-descriptions-item label="销量">{{ formatNumber(selectedCandidate.sales_count) }}</a-descriptions-item>
                <a-descriptions-item label="评分">{{ selectedCandidate.rating ?? '--' }}</a-descriptions-item>
                <a-descriptions-item label="来源链接" :span="2">
                  <a :href="selectedCandidate.source_url" target="_blank" rel="noreferrer">{{ selectedCandidate.source_url }}</a>
                </a-descriptions-item>
              </a-descriptions>
            </a-col>
          </a-row>

          <a-row :gutter="16">
            <a-col :span="12">
              <a-card size="small" title="利润测算">
                <a-descriptions :column="1" size="small">
                  <a-descriptions-item label="推荐售价">
                    {{ formatCurrency(selectedCandidate.pricing_assessment?.recommended_price) }}
                  </a-descriptions-item>
                  <a-descriptions-item label="预估利润">
                    {{ formatCurrency(selectedCandidate.pricing_assessment?.estimated_margin) }}
                  </a-descriptions-item>
                  <a-descriptions-item label="毛利率">
                    {{ formatPercent(selectedCandidate.pricing_assessment?.margin_percentage) }}
                  </a-descriptions-item>
                  <a-descriptions-item label="结论">
                    {{ selectedCandidate.pricing_assessment?.profitability_decision ?? '--' }}
                  </a-descriptions-item>
                  <a-descriptions-item label="已选供给路径">
                    {{ selectedSupplierSelection?.selected_supplier?.supplier_name ?? '--' }}
                  </a-descriptions-item>
                  <a-descriptions-item label="选择原因">
                    {{ selectedSupplierSelection?.selection_reason ?? '--' }}
                  </a-descriptions-item>
                </a-descriptions>
              </a-card>
            </a-col>
            <a-col :span="12">
              <a-card size="small" title="风控结果">
                <a-descriptions :column="1" size="small">
                  <a-descriptions-item label="决策">
                    <a-tag :color="riskTag(selectedCandidate.risk_assessment?.decision).color">
                      {{ riskTag(selectedCandidate.risk_assessment?.decision).label }}
                    </a-tag>
                  </a-descriptions-item>
                  <a-descriptions-item label="风险分">
                    {{ formatNumber(selectedCandidate.risk_assessment?.score ?? null) }}
                  </a-descriptions-item>
                  <a-descriptions-item label="规则命中">
                    {{ selectedCandidate.risk_assessment?.rule_hits?.join(' / ') || '--' }}
                  </a-descriptions-item>
                  <a-descriptions-item label="备注">
                    {{ selectedCandidate.risk_assessment?.llm_notes ?? '--' }}
                  </a-descriptions-item>
                </a-descriptions>
              </a-card>
            </a-col>
          </a-row>

          <a-row v-if="selectedSupplierSelection?.ranked_supplier_paths?.length" :gutter="16">
            <a-col :span="24">
              <SupplierRankingCard :selection="selectedSupplierSelection" />
            </a-col>
          </a-row>

          <a-row :gutter="16">
            <a-col :span="12">
              <SupplierMatchesTable :suppliers="sortedSupplierMatches" selected-label="是否选中" />
            </a-col>
            <a-col :span="12">
              <a-card size="small" title="生成文案草稿">
                <a-list :data-source="selectedCandidate.listing_drafts" size="small">
                  <template #renderItem="{ item }">
                    <a-list-item>
                      <a-list-item-meta :title="`${item.language.toUpperCase()} · ${item.title}`" :description="item.bullets?.join(' / ') || '--'" />
                    </a-list-item>
                  </template>
                </a-list>
              </a-card>
            </a-col>
          </a-row>
        </template>
      </div>
    </a-card>
  </div>
</template>
