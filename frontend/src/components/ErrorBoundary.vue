<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'

interface Props {
  fallback?: string
}

const props = withDefaults(defineProps<Props>(), {
  fallback: '加载失败，请重试',
})

const emit = defineEmits<{
  retry: []
}>()

const error = ref<Error | null>(null)

onErrorCaptured((err) => {
  error.value = err
  return false
})

const handleRetry = () => {
  error.value = null
  emit('retry')
}
</script>

<template>
  <div v-if="error">
    <a-result status="error" :title="fallback" :sub-title="error.message">
      <template #extra>
        <a-button type="primary" @click="handleRetry">重试</a-button>
      </template>
    </a-result>
  </div>
  <slot v-else />
</template>
