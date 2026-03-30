<script setup lang="ts">
import { ReloadOutlined } from '@ant-design/icons-vue'
import { computed, ref } from 'vue'

import ActionDetailDrawer from '@/components/ActionDetailDrawer.vue'
import { formatDateTime } from '@/adapters/formatters'
import { getActionExecutionStatusMeta, getActionTypeMeta } from '@/adapters/statusMeta'
import { usePendingActionsQuery } from '@/queries/useOperationsQuery'
import type { PendingAction } from '@/types/operations'
import type { UUID } from '@/types/common'

const filters = ref({
  platform: undefined as string | undefined,
  region: undefined as string | undefined,
  action_type: undefined as string | undefined,
})

const selectedExecutionId = ref<UUID | null>(null)
const drawerOpen = ref(false)

const queryParams = computed(() => ({
  platform: filters.value.platform,
  region: filters.value.region,
  limit: 50,
}))

const pendingQuery = usePendingActionsQuery(queryParams)

const actions = computed(() => pendingQuery.data.value ?? [])

const actionTypeOptions = [
  { value: 'repricing', label: '重新定价' },
  { value: 'replenish', label: '补货' },
  { value: 'swap_content', label: '切换内容' },
  { value: 'expand_platform', label: '扩平台' },
  { value: 'delist', label: '下架' },
  { value: 'retire', label: '退场' },
]

const filteredActions = computed(() => {
  if (!filters.value.action_type) return actions.value
  return actions.value.filter((action) => action.action_type === filters.value.action_type)
})

function handleRowClick(record: PendingAction) {
  selectedExecutionId.value = record.execution_id
  drawerOpen.value = true
}

function handleDrawerSuccess() {
  void pendingQuery.refetch()
}

const columns = [
  {
    title: '动作类型',
    key: 'action_type',
    width: 120,
  },
  {
    title: 'SKU/Listing',
    key: 'target',
    width: 280,
  },
  {
    title: '目标类型',
    dataIndex: 'target_type',
    key: 'target_type',
    width: 120,
  },
  {
    title: '状态',
    key: 'status',
    width: 120,
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 160,
  },
]
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="待审批动作">
      <template #extra>
        <a-space>
          <a-button :loading="pendingQuery.isFetching.value" @click="pendingQuery.refetch()">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
        </a-space>
      </template>

      <div class="page-stack">
        <a-alert
          type="info"
          show-icon
          message="以下动作需要人工审批后才能执行。点击行查看详情并进行审批、拒绝、延后或回滚操作。"
        />

        <div class="filter-grid">
          <a-input v-model:value="filters.platform" placeholder="平台，如 temu / amazon" allow-clear />
          <a-input v-model:value="filters.region" placeholder="区域，如 us / uk" allow-clear />
          <a-select
            v-model:value="filters.action_type"
            allow-clear
            placeholder="动作类型"
            :options="actionTypeOptions"
          />
        </div>
      </div>
    </a-card>

    <a-card class="section-card" title="待审批列表">
      <a-table
        :data-source="filteredActions"
        :columns="columns"
        :loading="pendingQuery.isLoading.value"
        :pagination="false"
        row-key="execution_id"
        :custom-row="(record: PendingAction) => ({
          onClick: () => handleRowClick(record),
          style: { cursor: 'pointer' },
        })"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'action_type'">
            <a-tag :color="getActionTypeMeta(record.action_type).color">
              {{ getActionTypeMeta(record.action_type).label }}
            </a-tag>
          </template>

          <template v-else-if="column.key === 'target'">
            <div class="target-cell">
              <div v-if="record.product_variant_id" class="target-id">
                SKU: {{ record.product_variant_id }}
              </div>
              <div v-if="record.listing_id" class="target-id">
                Listing: {{ record.listing_id }}
              </div>
              <div v-if="!record.product_variant_id && !record.listing_id" class="muted-text">
                --
              </div>
            </div>
          </template>

          <template v-else-if="column.key === 'status'">
            <a-tag :color="getActionExecutionStatusMeta(record.status).color">
              {{ getActionExecutionStatusMeta(record.status).label }}
            </a-tag>
          </template>

          <template v-else-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>
        </template>
      </a-table>

      <a-empty v-if="!pendingQuery.isLoading.value && filteredActions.length === 0" description="暂无待审批动作" />
    </a-card>

    <ActionDetailDrawer
      v-model:open="drawerOpen"
      :execution-id="selectedExecutionId"
      @success="handleDrawerSuccess"
    />
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

.filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.target-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.target-id {
  font-size: 12px;
  font-family: monospace;
}

.muted-text {
  color: #8c8c8c;
}
</style>
