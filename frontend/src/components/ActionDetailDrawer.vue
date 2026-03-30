<script setup lang="ts">
import { CheckOutlined, CloseOutlined, ClockCircleOutlined, RollbackOutlined } from '@ant-design/icons-vue'
import { computed, ref, watch } from 'vue'
import { formatDateTime } from '@/adapters/formatters'
import { getActionExecutionStatusMeta, getActionTypeMeta } from '@/adapters/statusMeta'
import {
  useActionExecutionQuery,
  useApproveActionMutation,
  useRejectActionMutation,
  useDeferActionMutation,
  useRollbackActionMutation,
} from '@/queries/useOperationsQuery'
import type { UUID } from '@/types/common'

interface Props {
  open: boolean
  executionId: UUID | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  success: []
}>()

const operatorEmail = ref('admin@example.com')
const comment = ref('')
const reason = ref('')

const actionQuery = useActionExecutionQuery(computed(() => props.executionId))
const approveMutation = useApproveActionMutation()
const rejectMutation = useRejectActionMutation()
const deferMutation = useDeferActionMutation()
const rollbackMutation = useRollbackActionMutation()

const actionData = computed(() => actionQuery.data.value)
const statusMeta = computed(() => getActionExecutionStatusMeta(actionData.value?.status))
const typeMeta = computed(() => getActionTypeMeta(actionData.value?.action_type))

const canApprove = computed(() => actionData.value?.status === 'pending_approval')
const canReject = computed(() => actionData.value?.status === 'pending_approval')
const canDefer = computed(() => actionData.value?.status === 'pending_approval')
const canRollback = computed(() => actionData.value?.status === 'completed')

watch(
  () => props.open,
  (newOpen) => {
    if (!newOpen) {
      comment.value = ''
      reason.value = ''
    }
  }
)

const handleClose = () => {
  emit('update:open', false)
}

const handleApprove = async () => {
  if (!props.executionId) return

  try {
    await approveMutation.mutateAsync({
      executionId: props.executionId,
      payload: {
        approved_by: operatorEmail.value,
        comment: comment.value || undefined,
      },
    })
    emit('success')
    handleClose()
  } catch (error) {
    // Error handled by mutation
  }
}

const handleReject = async () => {
  if (!props.executionId) return

  try {
    await rejectMutation.mutateAsync({
      executionId: props.executionId,
      payload: {
        rejected_by: operatorEmail.value,
        comment: comment.value || undefined,
      },
    })
    emit('success')
    handleClose()
  } catch (error) {
    // Error handled by mutation
  }
}

const handleDefer = async () => {
  if (!props.executionId) return

  try {
    await deferMutation.mutateAsync({
      executionId: props.executionId,
      payload: {
        deferred_by: operatorEmail.value,
        comment: comment.value || undefined,
      },
    })
    emit('success')
    handleClose()
  } catch (error) {
    // Error handled by mutation
  }
}

const handleRollback = async () => {
  if (!props.executionId) return

  try {
    await rollbackMutation.mutateAsync({
      executionId: props.executionId,
      payload: {
        rolled_back_by: operatorEmail.value,
        reason: reason.value || undefined,
      },
    })
    emit('success')
    handleClose()
  } catch (error) {
    // Error handled by mutation
  }
}
</script>

<template>
  <a-drawer
    :open="open"
    :title="'动作详情'"
    :width="640"
    @close="handleClose"
  >
    <a-spin :spinning="actionQuery.isLoading.value">
      <div v-if="actionData" class="drawer-content">
        <a-descriptions :column="1" size="small" bordered>
          <a-descriptions-item label="执行 ID">
            {{ actionData.execution_id }}
          </a-descriptions-item>
          <a-descriptions-item label="动作类型">
            <a-tag :color="typeMeta.color">{{ typeMeta.label }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="statusMeta.color">{{ statusMeta.label }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="目标类型">
            {{ actionData.target_type }}
          </a-descriptions-item>
          <a-descriptions-item label="目标 ID">
            {{ actionData.target_id }}
          </a-descriptions-item>
          <a-descriptions-item label="审批人">
            {{ actionData.approved_by ?? '--' }}
          </a-descriptions-item>
          <a-descriptions-item label="审批时间">
            {{ actionData.approved_at ? formatDateTime(actionData.approved_at) : '--' }}
          </a-descriptions-item>
          <a-descriptions-item label="开始时间">
            {{ actionData.started_at ? formatDateTime(actionData.started_at) : '--' }}
          </a-descriptions-item>
          <a-descriptions-item label="完成时间">
            {{ actionData.completed_at ? formatDateTime(actionData.completed_at) : '--' }}
          </a-descriptions-item>
          <a-descriptions-item v-if="actionData.error_message" label="错误信息">
            <a-alert type="error" :message="actionData.error_message" show-icon />
          </a-descriptions-item>
        </a-descriptions>

        <a-divider>输入参数</a-divider>
        <pre class="json-display">{{ JSON.stringify(actionData.input_params, null, 2) }}</pre>

        <a-divider v-if="actionData.output_data">输出数据</a-divider>
        <pre v-if="actionData.output_data" class="json-display">{{ JSON.stringify(actionData.output_data, null, 2) }}</pre>

        <a-divider>操作</a-divider>

        <div class="action-form">
          <a-input
            v-model:value="operatorEmail"
            placeholder="操作人邮箱"
            :disabled="!canApprove && !canReject && !canDefer && !canRollback"
          />

          <a-textarea
            v-if="canRollback"
            v-model:value="reason"
            placeholder="回滚原因（可选）"
            :rows="3"
            :maxlength="500"
            show-count
          />

          <a-textarea
            v-else
            v-model:value="comment"
            placeholder="备注（可选）"
            :rows="3"
            :maxlength="500"
            show-count
          />

          <a-space>
            <a-button
              v-if="canApprove"
              type="primary"
              :loading="approveMutation.isPending.value"
              @click="handleApprove"
            >
              <template #icon><CheckOutlined /></template>
              审批通过
            </a-button>

            <a-button
              v-if="canReject"
              danger
              :loading="rejectMutation.isPending.value"
              @click="handleReject"
            >
              <template #icon><CloseOutlined /></template>
              拒绝
            </a-button>

            <a-button
              v-if="canDefer"
              :loading="deferMutation.isPending.value"
              @click="handleDefer"
            >
              <template #icon><ClockCircleOutlined /></template>
              延后
            </a-button>

            <a-button
              v-if="canRollback"
              danger
              :loading="rollbackMutation.isPending.value"
              @click="handleRollback"
            >
              <template #icon><RollbackOutlined /></template>
              回滚
            </a-button>
          </a-space>
        </div>
      </div>

      <a-empty v-else description="无数据" />
    </a-spin>
  </a-drawer>
</template>

<style scoped>
.drawer-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.json-display {
  background-color: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
}

.action-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
