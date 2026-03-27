<script setup lang="ts">
import { CheckOutlined, CloseOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'

import { formatCurrency, formatDateTime, formatPercent } from '@/adapters/formatters'
import { sourcePlatformLabel } from '@/adapters/statusMeta'
import {
  usePendingApprovalsQuery,
  useApproveListingMutation,
  useRejectListingMutation,
} from '@/queries/useAutoActionsQuery'
import type { PendingApprovalListing } from '@/types/autoActions'

const router = useRouter()

const filters = ref({
  platform: undefined as string | undefined,
  limit: 20,
})

const selectedListing = ref<PendingApprovalListing>()
const approvalModalOpen = ref(false)
const rejectModalOpen = ref(false)
const approvalForm = ref({
  approved_by: 'admin@example.com',
  reason: '',
})

const pendingQuery = usePendingApprovalsQuery(filters)
const approveMutation = useApproveListingMutation()
const rejectMutation = useRejectListingMutation()

const listings = computed(() => pendingQuery.data.value?.items ?? [])
const sourceLabel = (source?: string) => sourcePlatformLabel[source ?? ''] ?? source ?? '--'

const approvalReasonLabel: Record<string, string> = {
  first_time_product: '首次上架',
  high_risk: '高风险品类',
  high_price: '高价商品',
  low_margin: '低利润率',
}

function handleApprove(listing: PendingApprovalListing) {
  selectedListing.value = listing
  approvalModalOpen.value = true
}

function handleReject(listing: PendingApprovalListing) {
  selectedListing.value = listing
  rejectModalOpen.value = true
}

async function confirmApprove() {
  if (!selectedListing.value) return

  try {
    await approveMutation.mutateAsync({
      listingId: selectedListing.value.id,
      payload: {
        approved_by: approvalForm.value.approved_by,
      },
    })
    approvalModalOpen.value = false
    selectedListing.value = undefined
  } catch (error) {
    // Error handled by mutation
  }
}

async function confirmReject() {
  if (!selectedListing.value) return

  if (!approvalForm.value.reason) {
    message.error('请填写拒绝原因')
    return
  }

  try {
    await rejectMutation.mutateAsync({
      listingId: selectedListing.value.id,
      payload: {
        approved_by: approvalForm.value.approved_by,
        reason: approvalForm.value.reason,
      },
    })
    rejectModalOpen.value = false
    selectedListing.value = undefined
    approvalForm.value.reason = ''
  } catch (error) {
    // Error handled by mutation
  }
}

function handleViewCandidate(candidateId: string) {
  router.push(`/candidates?id=${candidateId}`)
}

const columns = [
  {
    title: '平台',
    dataIndex: 'platform',
    key: 'platform',
    width: 100,
  },
  {
    title: '区域',
    dataIndex: 'region',
    key: 'region',
    width: 80,
  },
  {
    title: '价格',
    key: 'price',
    width: 120,
  },
  {
    title: '推荐分数',
    key: 'recommendation_score',
    width: 120,
  },
  {
    title: '风险分数',
    key: 'risk_score',
    width: 120,
  },
  {
    title: '利润率',
    key: 'margin_percentage',
    width: 120,
  },
  {
    title: '审批原因',
    key: 'approval_reason',
    width: 140,
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 160,
  },
  {
    title: '操作',
    key: 'actions',
    width: 200,
    fixed: 'right' as const,
  },
]
</script>

<template>
  <div class="page-stack">
    <a-card class="section-card" title="审批工作台">
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
          message="以下商品需要人工审批后才能发布到平台。审批决策基于服务端重新计算的真实指标（推荐分数、风险分数、利润率）。"
        />

        <div class="filter-grid">
          <a-input v-model:value="filters.platform" placeholder="平台，如 temu / amazon" allow-clear />
          <a-button type="primary" @click="pendingQuery.refetch()">查询</a-button>
        </div>
      </div>
    </a-card>

    <a-card class="section-card" title="待审批列表">
      <a-table
        :data-source="listings"
        :columns="columns"
        :loading="pendingQuery.isLoading.value"
        :pagination="false"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'price'">
            {{ formatCurrency(record.price, record.currency) }}
          </template>

          <template v-else-if="column.key === 'recommendation_score'">
            <a-tag v-if="record.auto_action_metadata?.recommendation_score" color="blue">
              {{ record.auto_action_metadata.recommendation_score.toFixed(1) }}
            </a-tag>
            <span v-else>--</span>
          </template>

          <template v-else-if="column.key === 'risk_score'">
            <a-tag
              v-if="record.auto_action_metadata?.risk_score"
              :color="record.auto_action_metadata.risk_score >= 50 ? 'red' : 'green'"
            >
              {{ record.auto_action_metadata.risk_score }}
            </a-tag>
            <span v-else>--</span>
          </template>

          <template v-else-if="column.key === 'margin_percentage'">
            <a-tag
              v-if="record.auto_action_metadata?.margin_percentage"
              :color="record.auto_action_metadata.margin_percentage >= 35 ? 'green' : 'orange'"
            >
              {{ formatPercent(record.auto_action_metadata.margin_percentage) }}
            </a-tag>
            <span v-else>--</span>
          </template>

          <template v-else-if="column.key === 'approval_reason'">
            <a-tag color="warning">
              {{ approvalReasonLabel[record.approval_reason ?? ''] ?? record.approval_reason ?? '--' }}
            </a-tag>
          </template>

          <template v-else-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>

          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button type="link" size="small" @click="handleViewCandidate(record.candidate_product_id)">
                查看候选
              </a-button>
              <a-button type="primary" size="small" @click="handleApprove(record)">
                <template #icon><CheckOutlined /></template>
                通过
              </a-button>
              <a-button danger size="small" @click="handleReject(record)">
                <template #icon><CloseOutlined /></template>
                拒绝
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>

      <a-empty v-if="!pendingQuery.isLoading.value && listings.length === 0" description="暂无待审批商品" />
    </a-card>

    <!-- 审批通过 Modal -->
    <a-modal
      v-model:open="approvalModalOpen"
      title="审批通过"
      ok-text="确认通过"
      cancel-text="取消"
      :confirm-loading="approveMutation.isPending.value"
      @ok="confirmApprove"
    >
      <div class="page-stack">
        <a-alert type="success" show-icon message="确认通过后，商品将自动发布到平台" />

        <a-descriptions v-if="selectedListing" :column="1" size="small" bordered>
          <a-descriptions-item label="平台">
            {{ sourceLabel(selectedListing.platform) }}
          </a-descriptions-item>
          <a-descriptions-item label="区域">{{ selectedListing.region }}</a-descriptions-item>
          <a-descriptions-item label="价格">
            {{ formatCurrency(selectedListing.price, selectedListing.currency) }}
          </a-descriptions-item>
          <a-descriptions-item label="推荐分数">
            {{ selectedListing.auto_action_metadata?.recommendation_score?.toFixed(1) ?? '--' }}
          </a-descriptions-item>
          <a-descriptions-item label="风险分数">
            {{ selectedListing.auto_action_metadata?.risk_score ?? '--' }}
          </a-descriptions-item>
          <a-descriptions-item label="利润率">
            {{ formatPercent(selectedListing.auto_action_metadata?.margin_percentage) }}
          </a-descriptions-item>
        </a-descriptions>

        <a-input v-model:value="approvalForm.approved_by" placeholder="审批人邮箱" />
      </div>
    </a-modal>

    <!-- 审批拒绝 Modal -->
    <a-modal
      v-model:open="rejectModalOpen"
      title="审批拒绝"
      ok-text="确认拒绝"
      cancel-text="取消"
      :confirm-loading="rejectMutation.isPending.value"
      @ok="confirmReject"
    >
      <div class="page-stack">
        <a-alert type="error" show-icon message="确认拒绝后，商品将不会发布到平台" />

        <a-descriptions v-if="selectedListing" :column="1" size="small" bordered>
          <a-descriptions-item label="平台">
            {{ sourceLabel(selectedListing.platform) }}
          </a-descriptions-item>
          <a-descriptions-item label="区域">{{ selectedListing.region }}</a-descriptions-item>
          <a-descriptions-item label="价格">
            {{ formatCurrency(selectedListing.price, selectedListing.currency) }}
          </a-descriptions-item>
        </a-descriptions>

        <a-input v-model:value="approvalForm.approved_by" placeholder="审批人邮箱" />
        <a-textarea
          v-model:value="approvalForm.reason"
          placeholder="请填写拒绝原因（必填）"
          :rows="3"
          :maxlength="500"
          show-count
        />
      </div>
    </a-modal>
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
</style>
