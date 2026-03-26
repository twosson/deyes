<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  status: string
  meta?: { label: string; color: string }
}

const props = defineProps<Props>()

const statusColorMap: Record<string, string> = {
  draft: 'blue',
  active: 'green',
  completed: 'purple',
  archived: 'default',
  pending: 'orange',
  running: 'cyan',
  failed: 'red',
  success: 'green',
}

const tagColor = computed(() => {
  if (props.meta) {
    return props.meta.color
  }
  return statusColorMap[props.status.toLowerCase()] ?? 'default'
})

const tagLabel = computed(() => {
  if (props.meta) {
    return props.meta.label
  }
  return props.status
})
</script>

<template>
  <a-tag :color="tagColor">
    <slot>{{ tagLabel }}</slot>
  </a-tag>
</template>
