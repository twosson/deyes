<script setup lang="ts">
import { computed } from 'vue'

import { formatCurrency, formatNumber } from '@/adapters/formatters'
import {
  getCheapestSupplierPrice,
  supplierPricePremiumLabel,
  supplierScoreBreakdownItems,
  supplierScoreBreakdownPreviewItems,
  supplierScoreColor,
  supplierSelectionTag,
} from '@/adapters/supplierHelpers'
import type { SupplierSelectionExplanation } from '@/types/candidates'

interface Props {
  selection: SupplierSelectionExplanation | null
}

const props = defineProps<Props>()

const cheapestPrice = computed(() =>
  getCheapestSupplierPrice(props.selection?.ranked_supplier_paths),
)
</script>

<template>
  <a-card v-if="selection?.ranked_supplier_paths?.length" size="small" title="供给路径排序说明">
    <a-table
      :data-source="selection.ranked_supplier_paths"
      :pagination="false"
      row-key="supplier_match_id"
      size="small"
    >
      <a-table-column title="排名" data-index="rank" key="rank" :width="70" />
      <a-table-column title="供应商" data-index="supplier_name" key="supplier_name" />
      <a-table-column title="状态" key="supplier_state" :width="120">
        <template #default="{ record }">
          <a-tag :color="record.supplier_match_id === selection?.selected_supplier?.supplier_match_id ? 'success' : supplierSelectionTag(record).color">
            {{ record.supplier_match_id === selection?.selected_supplier?.supplier_match_id ? '当前已选' : supplierSelectionTag(record).label }}
          </a-tag>
        </template>
      </a-table-column>
      <a-table-column title="身份信号" key="identity_signals" :width="180">
        <template #default="{ record }">
          <a-space wrap size="small">
            <a-tag v-if="record.identity_signals.is_factory_result" color="green">工厂</a-tag>
            <a-tag v-if="record.identity_signals.verified_supplier" color="blue">认证</a-tag>
            <a-tag v-if="record.identity_signals.is_super_factory" color="purple">超级工厂</a-tag>
            <a-tag v-if="record.identity_signals.alternative_sku" color="orange">备选SKU</a-tag>
            <span
              v-if="!record.identity_signals.is_factory_result && !record.identity_signals.verified_supplier && !record.identity_signals.is_super_factory && !record.identity_signals.alternative_sku"
            >--</span>
          </a-space>
        </template>
      </a-table-column>
      <a-table-column title="供货价" key="supplier_price" :width="120">
        <template #default="{ record }">{{ formatCurrency(record.supplier_price) }}</template>
      </a-table-column>
      <a-table-column title="相对最低价" key="price_premium" :width="120">
        <template #default="{ record }">
          {{ supplierPricePremiumLabel(record, cheapestPrice) }}
        </template>
      </a-table-column>
      <a-table-column title="MOQ" data-index="moq" key="moq" :width="90" />
      <a-table-column title="置信度" key="confidence_score" :width="100">
        <template #default="{ record }">{{ record.confidence_score ?? '--' }}</template>
      </a-table-column>
      <a-table-column title="综合分" key="score" :width="100">
        <template #default="{ record }">
          <a-tag :color="supplierScoreColor(record)">{{ formatNumber(record.score) }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="评分拆解" key="score_breakdown" :width="220">
        <template #default="{ record }">
          <a-tooltip v-if="supplierScoreBreakdownItems(record).length">
            <template #title>
              <div class="score-breakdown-tooltip">
                <div v-for="item in supplierScoreBreakdownItems(record)" :key="item.label">
                  {{ item.label }}：{{ formatNumber(item.value) }}
                </div>
              </div>
            </template>
            <a-space wrap size="small">
              <a-tag v-for="item in supplierScoreBreakdownPreviewItems(record)" :key="item.label" color="default">
                {{ item.label }} {{ formatNumber(item.value) }}
              </a-tag>
              <a-tag v-if="supplierScoreBreakdownItems(record).length > 3" color="blue">更多</a-tag>
            </a-space>
          </a-tooltip>
          <span v-else>--</span>
        </template>
      </a-table-column>
    </a-table>
  </a-card>
</template>
