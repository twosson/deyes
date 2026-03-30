<script setup lang="ts">
import { computed } from 'vue'
import { getAnomalySeverityMeta } from '@/adapters/statusMeta'
import type { Anomaly } from '@/types/operations'

interface Props {
  anomaly: Anomaly
}

const props = defineProps<Props>()

const emit = defineEmits<{
  viewDetails: [anomaly: Anomaly]
}>()

const severityMeta = computed(() => getAnomalySeverityMeta(props.anomaly.severity))

const details = computed(() => props.anomaly.details ?? {})
const actualValue = computed(() => details.value.actual_value ?? details.value.recent_revenue ?? details.value.recent_refunds ?? details.value.available_inventory ?? details.value.recent_ctr ?? details.value.recent_cvr ?? details.value.delayed_orders ?? details.value.refund_count ?? null)
const expectedValue = computed(() => details.value.expected_value ?? details.value.prior_revenue ?? details.value.prior_refunds ?? details.value.threshold_days ?? details.value.prior_ctr ?? details.value.prior_cvr ?? null)
const deviationDisplay = computed(() => {
  const percentage = details.value.deviation_percentage ?? details.value.decline_percentage ?? details.value.increase_percentage ?? null
  if (percentage !== null && percentage !== undefined) {
    return `${percentage > 0 ? '+' : ''}${Number(percentage).toFixed(1)}%`
  }
  return '--'
})
const detectedAt = computed(() => details.value.detected_at ?? null)

const handleViewDetails = () => {
  emit('viewDetails', props.anomaly)
}
</script>

<template>
  <a-card size="small" hoverable @click="handleViewDetails">
    <template #title>
      <a-space>
        <a-tag :color="severityMeta.color">{{ severityMeta.label }}</a-tag>
        <span>{{ anomaly.type }}</span>
      </a-space>
    </template>

    <a-descriptions :column="1" size="small">
      <a-descriptions-item label="SKU ID">{{ anomaly.product_variant_id ?? '--' }}</a-descriptions-item>
      <a-descriptions-item label="实际值">
        {{ actualValue ?? '--' }}
      </a-descriptions-item>
      <a-descriptions-item label="参考值">
        {{ expectedValue ?? '--' }}
      </a-descriptions-item>
      <a-descriptions-item label="偏差">
        <a-tag :color="deviationDisplay !== '--' ? 'orange' : 'default'">
          {{ deviationDisplay }}
        </a-tag>
      </a-descriptions-item>
      <a-descriptions-item label="检测时间">
        {{ detectedAt ?? '--' }}
      </a-descriptions-item>
    </a-descriptions>
  </a-card>
</template>

<style scoped>
.ant-card {
  cursor: pointer;
  transition: all 0.3s;
}

.ant-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
</style>
