<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import SupplierMatchesTable from '@/components/SupplierMatchesTable.vue'
import SupplierRankingCard from '@/components/SupplierRankingCard.vue'
import { formatCurrency, formatDateTime, formatNumber } from '@/adapters/formatters'
import { assetTypeLabel, lifecycleMeta, listingStatusMeta, sourcePlatformLabel } from '@/adapters/statusMeta'
import { useProductDetailQuery } from '@/queries/useProductsQuery'

const route = useRoute()
const productId = computed(() => String(route.params.id ?? ''))
const productQuery = useProductDetailQuery(productId)
const product = computed(() => productQuery.data.value)
const supplierSelection = computed(
  () => product.value?.pricing_assessment?.explanation?.supplier_selection ?? null,
)
const sortedSupplierMatches = computed(() => {
  if (!product.value?.supplier_matches) return []
  const matches = [...product.value.supplier_matches]
  return matches.sort((a, b) => {
    if (a.selected && !b.selected) return -1
    if (!a.selected && b.selected) return 1
    return 0
  })
})

const lifecycleTag = (status?: string | null) => lifecycleMeta[status ?? ''] ?? { label: status ?? '--', color: 'default' }
const listingTag = (status?: string | null) => listingStatusMeta[status ?? ''] ?? { label: status ?? '--', color: 'default' }
const sourceLabel = (source?: string) => sourcePlatformLabel[source ?? ''] ?? source ?? '--'
const assetLabel = (assetType?: string | null) => assetTypeLabel[assetType ?? ''] ?? assetType ?? '--'
</script>

<template>
  <div class="page-stack">
    <a-skeleton v-if="productQuery.isLoading.value" active />

    <template v-else-if="product">
      <a-card class="section-card" title="商品概览">
        <div class="two-column-grid">
          <div>
            <div v-if="product.main_image_url" style="max-width: 360px">
              <a-image :src="product.main_image_url" width="100%" />
            </div>
            <div v-else class="image-placeholder">暂无主图</div>
          </div>

          <div class="panel-stack">
            <a-descriptions bordered :column="2" size="small">
              <a-descriptions-item label="标题" :span="2">{{ product.title }}</a-descriptions-item>
              <a-descriptions-item label="内部 SKU">{{ product.internal_sku ?? '--' }}</a-descriptions-item>
              <a-descriptions-item label="类目">{{ product.category ?? '--' }}</a-descriptions-item>
              <a-descriptions-item label="来源平台">{{ sourceLabel(product.source_platform) }}</a-descriptions-item>
              <a-descriptions-item label="来源商品 ID">{{ product.source_product_id ?? '--' }}</a-descriptions-item>
              <a-descriptions-item label="平台价">{{ formatCurrency(product.platform_price) }}</a-descriptions-item>
              <a-descriptions-item label="销量">{{ formatNumber(product.sales_count) }}</a-descriptions-item>
              <a-descriptions-item label="评分">{{ product.rating ?? '--' }}</a-descriptions-item>
              <a-descriptions-item label="生命周期">
                <a-tag :color="lifecycleTag(product.lifecycle_status).color">{{ lifecycleTag(product.lifecycle_status).label }}</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="创建时间">{{ formatDateTime(product.created_at) }}</a-descriptions-item>
              <a-descriptions-item label="推荐售价">
                {{ formatCurrency(product.pricing_assessment?.recommended_price ?? null) }}
              </a-descriptions-item>
              <a-descriptions-item label="毛利率">
                {{ formatNumber(product.pricing_assessment?.margin_percentage ?? null) }}
              </a-descriptions-item>
              <a-descriptions-item label="已选供给路径" :span="2">
                {{ supplierSelection?.selected_supplier?.supplier_name ?? '--' }}
              </a-descriptions-item>
              <a-descriptions-item label="选择原因" :span="2">
                {{ supplierSelection?.selection_reason ?? '--' }}
              </a-descriptions-item>
              <a-descriptions-item label="来源链接" :span="2">
                <a v-if="product.source_url" :href="product.source_url" target="_blank" rel="noreferrer">{{ product.source_url }}</a>
                <span v-else>--</span>
              </a-descriptions-item>
            </a-descriptions>
          </div>
        </div>
      </a-card>

      <a-tabs>
        <a-tab-pane key="assets" tab="内容资产">
          <a-table :data-source="product.assets" :pagination="false" row-key="id" size="small">
            <a-table-column title="类型" key="asset_type">
              <template #default="{ record }">{{ assetLabel(record.asset_type) }}</template>
            </a-table-column>
            <a-table-column title="风格" key="style_tags">
              <template #default="{ record }">{{ record.style_tags?.join(' / ') || '--' }}</template>
            </a-table-column>
            <a-table-column title="质量分" key="ai_quality_score">
              <template #default="{ record }">{{ record.ai_quality_score ?? '--' }}</template>
            </a-table-column>
            <a-table-column title="审核" key="human_approved">
              <template #default="{ record }">
                <a-tag :color="record.human_approved ? 'success' : 'default'">{{ record.human_approved ? '已通过' : '未通过' }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column title="文件">
              <template #default="{ record }">
                <a :href="record.file_url" target="_blank" rel="noreferrer">查看</a>
              </template>
            </a-table-column>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="listings" tab="平台发布">
          <a-table :data-source="product.listings" :pagination="false" row-key="id" size="small">
            <a-table-column title="平台" data-index="platform" key="platform" />
            <a-table-column title="区域" data-index="region" key="region" />
            <a-table-column title="价格" key="price">
              <template #default="{ record }">{{ formatCurrency(record.price, record.currency) }}</template>
            </a-table-column>
            <a-table-column title="库存" data-index="inventory" key="inventory" />
            <a-table-column title="状态" key="status">
              <template #default="{ record }">
                <a-tag :color="listingTag(record.status).color">{{ listingTag(record.status).label }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column title="同步错误" data-index="sync_error" key="sync_error" ellipsis />
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="suppliers" tab="供应商匹配">
          <SupplierRankingCard :selection="supplierSelection" style="margin-bottom: 16px" />

          <SupplierMatchesTable :suppliers="sortedSupplierMatches" />
        </a-tab-pane>
      </a-tabs>
    </template>
  </div>
</template>
