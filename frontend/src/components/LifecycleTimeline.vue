<script setup lang="ts">
import { computed } from 'vue'
import { formatDateTime } from '@/adapters/formatters'
import { getSkuLifecycleStateMeta } from '@/adapters/statusMeta'
import type { SkuLifecycleState } from '@/types/operations'

interface Props {
  currentState: SkuLifecycleState
  enteredAt: string | null
  confidenceScore?: number
}

const props = defineProps<Props>()

const lifecycleStates: SkuLifecycleState[] = [
  'discovering',
  'testing',
  'scaling',
  'stable',
  'declining',
  'clearance',
  'retired',
]

const timelineItems = computed(() => {
  const currentIndex = lifecycleStates.indexOf(props.currentState)

  return lifecycleStates.map((state, index) => {
    const meta = getSkuLifecycleStateMeta(state)
    const isCurrent = state === props.currentState
    const isPast = index < currentIndex
    const isFuture = index > currentIndex

    let color = 'gray'
    if (isCurrent) {
      color = meta.color
    } else if (isPast) {
      color = 'green'
    }

    return {
      state,
      label: meta.label,
      color,
      isCurrent,
      isPast,
      isFuture,
    }
  })
})

const currentStateMeta = computed(() => getSkuLifecycleStateMeta(props.currentState))
</script>

<template>
  <div class="lifecycle-timeline">
    <a-alert type="info" show-icon>
      <template #message>
        <a-space>
          <span>当前状态:</span>
          <a-tag :color="currentStateMeta.color">{{ currentStateMeta.label }}</a-tag>
          <span v-if="enteredAt">进入时间: {{ formatDateTime(enteredAt) }}</span>
          <span v-if="confidenceScore">置信度: {{ confidenceScore.toFixed(2) }}</span>
        </a-space>
      </template>
    </a-alert>

    <a-timeline mode="left">
      <a-timeline-item
        v-for="item in timelineItems"
        :key="item.state"
        :color="item.color"
      >
        <template #dot>
          <span
            v-if="item.isCurrent"
            class="current-dot"
            :style="{ backgroundColor: item.color }"
          />
        </template>

        <div class="timeline-content">
          <a-tag :color="item.color">{{ item.label }}</a-tag>
          <span v-if="item.isCurrent" class="current-label">（当前）</span>
          <span v-else-if="item.isPast" class="past-label">（已完成）</span>
          <span v-else class="future-label">（未来）</span>
        </div>
      </a-timeline-item>
    </a-timeline>
  </div>
</template>

<style scoped>
.lifecycle-timeline {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.current-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(1.2);
  }
}

.timeline-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.current-label {
  font-weight: 600;
  color: #1890ff;
}

.past-label {
  color: #52c41a;
}

.future-label {
  color: #8c8c8c;
}
</style>
