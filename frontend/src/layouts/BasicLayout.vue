<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useUiStore } from '@/app/stores/ui'

const route = useRoute()
const router = useRouter()
const uiStore = useUiStore()

const menuItems = [
  { key: '/dashboard', label: '工作台' },
  { key: '/candidates', label: '选品岗位' },
  { key: '/recommendations', label: '智能推荐' },
  { key: '/products', label: '商品中心' },
  { key: '/content-assets', label: '内容中心' },
  { key: '/experiments', label: 'A/B测试实验' },
  { key: '/platform-listings', label: '发布中心' },
  { key: '/task-monitor', label: '任务监控' },
  { key: '/analytics', label: '数据看板' },
]

const selectedKeys = computed(() => [String(route.meta.menuKey ?? route.path)])
const pageTitle = computed(() => String(route.meta.title ?? 'Deyes 运营中台'))
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

function handleMenuClick({ key }: { key: string }) {
  void router.push(key)
}
</script>

<template>
  <a-layout class="basic-layout">
    <a-layout-sider
      :collapsed="uiStore.siderCollapsed"
      collapsible
      breakpoint="lg"
      @collapse="uiStore.setSiderCollapsed"
    >
      <div class="layout-logo">
        <strong>Deyes</strong>
        <span v-if="!uiStore.siderCollapsed">运营中台</span>
      </div>
      <a-menu
        theme="dark"
        mode="inline"
        :selected-keys="selectedKeys"
        :items="menuItems"
        @click="handleMenuClick"
      />
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="layout-header">
        <div>
          <h1 class="layout-title">{{ pageTitle }}</h1>
          <p class="layout-subtitle">选品、内容、发布与监控统一入口</p>
        </div>
        <a-space>
          <a-tag color="processing">独立前端</a-tag>
          <a-tag>{{ apiBaseUrl }}</a-tag>
        </a-space>
      </a-layout-header>

      <a-layout-content class="layout-content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>
