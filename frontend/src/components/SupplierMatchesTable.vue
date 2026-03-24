<script setup lang="ts">
import { formatCurrency } from '@/adapters/formatters'
import type { SupplierMatch } from '@/types/candidates'

interface Props {
  suppliers: SupplierMatch[]
  title?: string
  selectedLabel?: string
}

withDefaults(defineProps<Props>(), {
  title: '供应商匹配',
  selectedLabel: '已选择',
})
</script>

<template>
  <a-card size="small" :title="title">
    <a-table :data-source="suppliers" :pagination="false" row-key="id" size="small">
      <a-table-column title="供应商" data-index="supplier_name" key="supplier_name" ellipsis />
      <a-table-column title="供货价" key="supplier_price">
        <template #default="{ record }">{{ formatCurrency(record.supplier_price) }}</template>
      </a-table-column>
      <a-table-column title="MOQ" data-index="moq" key="moq" />
      <a-table-column :title="selectedLabel" key="selected" :width="100">
        <template #default="{ record }">
          <a-tag :color="record.selected ? 'success' : 'default'">{{ record.selected ? '是' : '否' }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="置信度" key="confidence_score">
        <template #default="{ record }">{{ record.confidence_score ?? '--' }}</template>
      </a-table-column>
    </a-table>
  </a-card>
</template>
