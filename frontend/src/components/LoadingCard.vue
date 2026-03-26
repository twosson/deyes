<script setup lang="ts">
interface Props {
  loading: boolean
  title?: string
}

defineProps<Props>()
</script>

<template>
  <a-card v-if="loading" :title="title">
    <a-skeleton active />
  </a-card>
  <a-card v-else :title="title">
    <slot />
  </a-card>
</template>
