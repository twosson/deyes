<script setup lang="ts">
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { formatDateTime } from '@/adapters/formatters'
import CreateExperimentModal from './CreateExperimentModal.vue'
import {
  useActivateExperimentMutation,
  useExperimentsQuery,
} from '@/queries/useExperimentsQuery'
import { ExperimentStatus } from '@/types/experiments'
import type { Experiment } from '@/types/experiments'

const router = useRouter()
const createModalVisible = ref(false)

const filters = reactive({
  status: undefined as string | undefined,
  limit: 20,
  offset: 0,
})

const queryParams = computed(() => ({
  status: filters.status,
  limit: filters.limit,
  offset: filters.offset,
}))

const experimentsQuery = useExperimentsQuery(queryParams)
const activateMutation = useActivateExperimentMutation()

const experiments = computed(() => experimentsQuery.data.value?.experiments ?? [])
const total = computed(() => experimentsQuery.data.value?.total ?? 0)

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

function getStatusColor(status: string) {
  return statusColorMap[status] ?? 'default'
}

function getStatusLabel(status: string) {
  return statusLabelMap[status] ?? status
}

function viewDetail(experimentId: string) {
  void router.push(`/experiments/${experimentId}`)
}

async function handleActivate(experimentId: string) {
  await activateMutation.mutateAsync(experimentId)
}

function handlePageChange(page: number, size: number) {
  filters.limit = size
  filters.offset = (page - 1) * size
}

const columns = [
  { title: '实验名称', dataIndex: 'name', key: 'name', width: 200 },
  { title: '商品ID', dataIndex: 'candidate_product_id', key: 'candidate_product_id', width: 280, ellipsis: true },
  { title: '目标指标', dataIndex: 'metric_goal', key: 'metric_goal', width: 100 },
  { title: '平台', dataIndex: 'target_platform', key: 'target_platform', width: 100 },
  { title: '区域', dataIndex: 'region', key: 'region', width: 80 },
  { title: '状态', key: 'status', width: 100 },
  { title: '获胜变体', dataIndex: 'winner_variant_group', key: 'winner_variant_group', width: 100 },
  { title: '创建时间', key: 'created_at', width: 150 },
  { title: '操作', key: 'actions', width: 180, fixed: 'right' as const },
]
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="A/B测试实验">
      <template #extra>
        <a-button type="primary" @click="createModalVisible = true">
          <template #icon><PlusOutlined /></template>
          创建实验
        </a-button>
      </template>

      <div class="filter-grid">
        <a-select
          v-model:value="filters.status"
          allow-clear
          placeholder="状态"
          style="width: 150px"
        >
          <a-select-option value="">全部</a-select-option>
          <a-select-option :value="ExperimentStatus.DRAFT">草稿</a-select-option>
          <a-select-option :value="ExperimentStatus.ACTIVE">进行中</a-select-option>
          <a-select-option :value="ExperimentStatus.COMPLETED">已完成</a-select-option>
          <a-select-option :value="ExperimentStatus.ARCHIVED">已归档</a-select-option>
        </a-select>
        <a-space>
          <a-button type="primary" @click="experimentsQuery.refetch()">查询</a-button>
          <a-button @click="experimentsQuery.refetch()">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
        </a-space>
      </div>
    </a-card>

    <a-card class="section-card" title="实验列表">
      <a-table
        :columns="columns"
        :data-source="experiments"
        :loading="experimentsQuery.isLoading.value"
        :pagination="false"
        row-key="id"
      >
        <template #bodyCell="{ column, record }: { column: any; record: Experiment }">
          <template v-if="column.key === 'status'">
            <a-tag :color="getStatusColor(record.status)">
              {{ getStatusLabel(record.status) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button size="small" @click="viewDetail(record.id)">查看</a-button>
              <a-button
                v-if="record.status === ExperimentStatus.DRAFT"
                size="small"
                type="primary"
                :loading="activateMutation.isPending.value"
                @click="handleActivate(record.id)"
              >
                激活
              </a-button>
            </a-space>
          </template>
        </template>
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

    <CreateExperimentModal v-model:visible="createModalVisible" />
  </div>
</template>
