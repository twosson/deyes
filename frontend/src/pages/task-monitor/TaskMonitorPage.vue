<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { formatDateTime, formatNumber } from '@/adapters/formatters'
import { sourcePlatformLabel } from '@/adapters/statusMeta'
import {
  useAgentRunResultsQuery,
  useAgentRunsListQuery,
  useAgentRunStepsQuery,
  useAgentRunStatusQuery,
} from '@/queries/useAgentRunsQuery'
import type { StrategyRunListItem } from '@/types/taskMonitor'

const selectedRunId = ref<string>()
const filters = reactive({
  status: undefined as string | undefined,
  source_platform: undefined as string | undefined,
  limit: 10,
  offset: 0,
})

const queryParams = computed(() => ({
  status: filters.status,
  source_platform: filters.source_platform,
  limit: filters.limit,
  offset: filters.offset,
}))

const runsQuery = useAgentRunsListQuery(queryParams)
const runStatusQuery = useAgentRunStatusQuery(selectedRunId)
const runStepsQuery = useAgentRunStepsQuery(selectedRunId)
const runResultsQuery = useAgentRunResultsQuery(selectedRunId)

const rows = computed(() => runsQuery.data.value?.runs ?? [])
const total = computed(() => runsQuery.data.value?.total ?? 0)
const steps = computed(() => runStepsQuery.data.value?.steps ?? [])
const candidates = computed(() => runResultsQuery.data.value?.candidates ?? [])
const sourceLabel = (source?: string | null) => sourcePlatformLabel[source ?? ''] ?? source ?? '--'
const runStatusLabel = (status?: string | null) => {
  if (status === 'queued') return '排队中'
  if (status === 'running') return '运行中'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  return status ?? '--'
}
const runStatusColor = (status?: string | null) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running') return 'processing'
  if (status === 'queued') return 'gold'
  return 'default'
}

watch(rows, (nextRows) => {
  if (nextRows.length === 0) {
    selectedRunId.value = undefined
    return
  }
  if (!selectedRunId.value || !nextRows.some((item) => item.run_id === selectedRunId.value)) {
    selectedRunId.value = nextRows[0].run_id
  }
}, { immediate: true })

function selectRun(record: StrategyRunListItem) {
  selectedRunId.value = record.run_id
}

function handlePageChange(page: number, size: number) {
  filters.limit = size
  filters.offset = (page - 1) * size
}
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="任务监控">
      <div class="filter-grid">
        <a-select
          v-model:value="filters.status"
          allow-clear
          placeholder="任务状态"
          :options="[
            { value: 'queued', label: '排队中' },
            { value: 'running', label: '运行中' },
            { value: 'completed', label: '已完成' },
            { value: 'failed', label: '失败' },
          ]"
        />
        <a-select
          v-model:value="filters.source_platform"
          allow-clear
          placeholder="来源平台"
          :options="[
            { value: 'alibaba_1688', label: '1688' },
            { value: 'temu', label: 'Temu' },
            { value: 'amazon', label: 'Amazon' },
          ]"
        />
        <a-space>
          <a-button type="primary" @click="runsQuery.refetch()">查询</a-button>
          <a-button @click="runsQuery.refetch()">刷新</a-button>
        </a-space>
      </div>
    </a-card>

    <div class="two-column-grid">
      <a-card class="section-card" title="策略任务列表">
        <a-table :data-source="rows" :loading="runsQuery.isLoading.value" :pagination="false" row-key="run_id" size="small">
          <a-table-column title="平台" key="source_platform" :width="90">
            <template #default="{ record }">{{ sourceLabel(record.source_platform) }}</template>
          </a-table-column>
          <a-table-column title="状态" key="status" :width="100">
            <template #default="{ record }">
              <a-tag :color="runStatusColor(record.status)">{{ runStatusLabel(record.status) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="类目" data-index="category" key="category" :width="120" ellipsis />
          <a-table-column title="当前步骤" data-index="current_step" key="current_step" :width="140" ellipsis />
          <a-table-column title="候选数" key="candidates_discovered" :width="90">
            <template #default="{ record }">{{ formatNumber(record.candidates_discovered) }}</template>
          </a-table-column>
          <a-table-column title="进度" key="progress" :width="100">
            <template #default="{ record }">{{ record.completed_steps }}/{{ record.total_steps }}</template>
          </a-table-column>
          <a-table-column title="创建时间" key="created_at" :width="150">
            <template #default="{ record }">{{ formatDateTime(record.created_at) }}</template>
          </a-table-column>
          <a-table-column title="操作" key="actions" :width="80">
            <template #default="{ record }">
              <a-button type="link" @click="selectRun(record)">查看</a-button>
            </template>
          </a-table-column>
        </a-table>

        <div style="display: flex; justify-content: flex-end; margin-top: 16px">
          <a-pagination
            :current="Math.floor(filters.offset / filters.limit) + 1"
            :page-size="filters.limit"
            :total="total"
            show-size-changer
            @change="handlePageChange"
          />
        </div>
      </a-card>

      <a-card class="section-card" title="任务详情">
        <a-empty v-if="!selectedRunId" description="选择左侧任务查看步骤和结果" />
        <div v-else class="page-stack">
          <a-descriptions bordered :column="1" size="small">
            <a-descriptions-item label="任务 ID">{{ selectedRunId }}</a-descriptions-item>
            <a-descriptions-item label="状态">
              <a-tag :color="runStatusColor(runStatusQuery.data.value?.status)">
                {{ runStatusLabel(runStatusQuery.data.value?.status) }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="当前步骤">{{ runStatusQuery.data.value?.current_step ?? '--' }}</a-descriptions-item>
            <a-descriptions-item label="候选数">{{ runStatusQuery.data.value?.candidates_discovered ?? 0 }}</a-descriptions-item>
            <a-descriptions-item label="进度">
              {{ runStatusQuery.data.value?.progress.completed_steps ?? 0 }}/{{ runStatusQuery.data.value?.progress.total_steps ?? 0 }}
            </a-descriptions-item>
          </a-descriptions>

          <a-card size="small" title="步骤执行记录">
            <a-empty v-if="steps.length === 0" description="暂无步骤记录" />
            <a-timeline v-else>
              <a-timeline-item v-for="step in steps" :key="step.id" :color="step.status === 'completed' ? 'green' : step.status === 'failed' ? 'red' : 'blue'">
                <div><strong>{{ step.step_name }}</strong> · {{ step.agent_name }}</div>
                <div class="muted-text">状态：{{ step.status }} / 尝试：{{ step.attempt }}</div>
                <div class="muted-text">开始：{{ formatDateTime(step.started_at) }}</div>
                <div v-if="step.completed_at" class="muted-text">完成：{{ formatDateTime(step.completed_at) }}</div>
                <div v-if="step.latency_ms !== null" class="muted-text">耗时：{{ formatNumber(step.latency_ms) }} ms</div>
                <div v-if="step.error_message" style="color: #cf1322">{{ step.error_message }}</div>
              </a-timeline-item>
            </a-timeline>
          </a-card>

          <a-card size="small" title="任务产出候选">
            <a-empty v-if="candidates.length === 0" description="暂无候选产出" />
            <a-list v-else :data-source="candidates" size="small">
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-list-item-meta :title="item.title" :description="`毛利率：${item.margin_percentage ?? '--'} / 风险：${item.risk_decision ?? '--'}`" />
                </a-list-item>
              </template>
            </a-list>
          </a-card>
        </div>
      </a-card>
    </div>
  </div>
</template>
