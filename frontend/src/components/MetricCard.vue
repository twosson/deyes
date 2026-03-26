<script setup lang="ts">
interface Trend {
  value: number
  isPositive: boolean
}

interface Props {
  title: string
  value: number | string
  suffix?: string
  prefix?: string
  trend?: Trend
  loading?: boolean
}

withDefaults(defineProps<Props>(), {
  loading: false,
})
</script>

<template>
  <a-card size="small" :loading="loading">
    <a-statistic :title="title" :value="value" :suffix="suffix" :prefix="prefix">
      <template v-if="trend" #suffix>
        <span>{{ suffix }}</span>
        <span
          :style="{
            marginLeft: '8px',
            color: trend.isPositive ? '#3f8600' : '#cf1322',
            fontSize: '14px',
          }"
        >
          {{ trend.isPositive ? '↑' : '↓' }} {{ Math.abs(trend.value) }}%
        </span>
      </template>
    </a-statistic>
  </a-card>
</template>
