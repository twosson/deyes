<script setup lang="ts">
import { computed } from 'vue'

import { formatNumber } from '@/adapters/formatters'
import { lifecycleMeta } from '@/adapters/statusMeta'
import { useCandidatesQuery } from '@/queries/useCandidatesQuery'
import { useContentAssetsQuery } from '@/queries/useContentAssetsQuery'
import { usePlatformListingsQuery } from '@/queries/usePlatformListingsQuery'
import { useProductStatsQuery } from '@/queries/useProductsQuery'

const productStatsQuery = useProductStatsQuery()
const candidatesQuery = useCandidatesQuery()
const assetsQuery = useContentAssetsQuery(computed(() => ({ limit: 5, offset: 0 })))
const listingsQuery = usePlatformListingsQuery(computed(() => ({ limit: 5, offset: 0 })))

const stats = computed(() => productStatsQuery.data.value)
const candidateItems = computed(() => candidatesQuery.data.value?.items?.slice(0, 5) ?? [])
const lifecycleItems = computed(() => Object.entries(stats.value?.by_lifecycle ?? {}))
const recentAssets = computed(() => assetsQuery.data.value?.assets ?? [])
const recentListings = computed(() => listingsQuery.data.value?.listings ?? [])

const lifecycleLabel = (status: string) => lifecycleMeta[status]?.label ?? status
</script>

<template>
  <div class="page-stack">
    <div class="kpi-grid">
      <a-card class="metric-card" title="商品总量">
        <div class="metric-value">{{ formatNumber(stats?.total_products ?? null) }}</div>
        <div class="muted-text">已进入中台管理的商品数</div>
      </a-card>
      <a-card class="metric-card" title="内容资产">
        <div class="metric-value">{{ formatNumber(stats?.total_assets ?? null) }}</div>
        <div class="muted-text">已生成素材总数</div>
      </a-card>
      <a-card class="metric-card" title="平台发布">
        <div class="metric-value">{{ formatNumber(stats?.total_listings ?? null) }}</div>
        <div class="muted-text">已创建 listing 总数</div>
      </a-card>
      <a-card class="metric-card" title="已发布商品">
        <div class="metric-value">{{ formatNumber(stats?.total_published ?? null) }}</div>
        <div class="muted-text">生命周期已进入发布阶段</div>
      </a-card>
    </div>

    <div class="two-column-grid">
      <a-card class="section-card" title="生命周期分布">
        <a-list :data-source="lifecycleItems" :loading="productStatsQuery.isLoading.value">
          <template #renderItem="{ item }">
            <a-list-item>
              <div style="display: flex; justify-content: space-between; width: 100%">
                <span>{{ lifecycleLabel(item[0]) }}</span>
                <strong>{{ item[1] }}</strong>
              </div>
            </a-list-item>
          </template>
        </a-list>
      </a-card>

      <a-card class="section-card" title="待处理候选商品">
        <a-list :data-source="candidateItems" :loading="candidatesQuery.isLoading.value">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta :title="item.title" :description="`风险：${item.risk_decision ?? '--'} / 毛利率：${item.margin_percentage ?? '--'}`" />
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </div>

    <div class="two-column-grid">
      <a-card class="section-card" title="最新内容资产">
        <a-list :data-source="recentAssets" :loading="assetsQuery.isLoading.value">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta :title="item.asset_type" :description="`质量分：${item.ai_quality_score ?? '--'} / 审核：${item.human_approved ? '通过' : '未通过'}`" />
            </a-list-item>
          </template>
        </a-list>
      </a-card>

      <a-card class="section-card" title="最新发布任务">
        <a-list :data-source="recentListings" :loading="listingsQuery.isLoading.value">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta :title="`${item.platform} · ${item.region}`" :description="`状态：${item.status} / 同步：${item.sync_status ?? '--'}`" />
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </div>
  </div>
</template>
