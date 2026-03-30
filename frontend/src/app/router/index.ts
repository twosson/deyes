import type { RouteRecordRaw } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'

const BasicLayout = () => import('@/layouts/BasicLayout.vue')
const AnalyticsPage = () => import('@/pages/analytics/AnalyticsPage.vue')
const ApprovalWorkbenchPage = () => import('@/pages/approval-workbench/ApprovalWorkbenchPage.vue')
const CandidatesPage = () => import('@/pages/candidates/CandidatesPage.vue')
const ContentAssetsPage = () => import('@/pages/content-assets/ContentAssetsPage.vue')
const DashboardPage = () => import('@/pages/dashboard/DashboardPage.vue')
const ExperimentDetailPage = () => import('@/pages/experiments/ExperimentDetailPage.vue')
const ExperimentsPage = () => import('@/pages/experiments/ExperimentsPage.vue')
const PerformanceMonitorPage = () => import('@/pages/performance/PerformanceMonitorPage.vue')
const PlatformListingsPage = () => import('@/pages/platform-listings/PlatformListingsPage.vue')
const ExceptionsPage = () => import('@/pages/operations/ExceptionsPage.vue')
const LifecyclePage = () => import('@/pages/operations/LifecyclePage.vue')
const OperationsDashboardPage = () => import('@/pages/operations/OperationsDashboardPage.vue')
const PendingActionsPage = () => import('@/pages/operations/PendingActionsPage.vue')
const ProductDetailPage = () => import('@/pages/products/ProductDetailPage.vue')
const ProductsPage = () => import('@/pages/products/ProductsPage.vue')
const TaskMonitorPage = () => import('@/pages/task-monitor/TaskMonitorPage.vue')

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: BasicLayout,
    children: [
      {
        path: '',
        redirect: '/dashboard',
      },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: DashboardPage,
        meta: { title: '工作台', menuKey: '/dashboard' },
      },
      {
        path: 'candidates',
        name: 'candidates',
        component: CandidatesPage,
        meta: { title: '选品岗位', menuKey: '/candidates' },
      },
      {
        path: 'products',
        name: 'products',
        component: ProductsPage,
        meta: { title: '商品中心', menuKey: '/products' },
      },
      {
        path: 'recommendations',
        name: 'recommendations',
        component: ApprovalWorkbenchPage,
        meta: { title: '审批工作台', menuKey: '/recommendations' },
      },
      {
        path: 'products/:id',
        name: 'product-detail',
        component: ProductDetailPage,
        meta: { title: '商品详情', menuKey: '/products' },
      },
      {
        path: 'content-assets',
        name: 'content-assets',
        component: ContentAssetsPage,
        meta: { title: '内容中心', menuKey: '/content-assets' },
      },
      {
        path: 'experiments',
        name: 'experiments',
        component: ExperimentsPage,
        meta: { title: 'A/B测试实验', menuKey: '/experiments' },
      },
      {
        path: 'experiments/:id',
        name: 'experiment-detail',
        component: ExperimentDetailPage,
        meta: { title: '实验详情', menuKey: '/experiments' },
      },
      {
        path: 'platform-listings',
        name: 'platform-listings',
        component: PlatformListingsPage,
        meta: { title: '发布中心', menuKey: '/platform-listings' },
      },
      {
        path: 'task-monitor',
        name: 'task-monitor',
        component: TaskMonitorPage,
        meta: { title: '任务监控', menuKey: '/task-monitor' },
      },
      {
        path: 'analytics',
        name: 'analytics',
        component: AnalyticsPage,
        meta: { title: '数据看板', menuKey: '/analytics' },
      },
      {
        path: 'performance',
        name: 'performance',
        component: PerformanceMonitorPage,
        meta: { title: '性能监控', menuKey: '/performance' },
      },
      {
        path: 'operations',
        name: 'operations',
        component: OperationsDashboardPage,
        meta: { title: '运营控制台', menuKey: '/operations' },
      },
      {
        path: 'operations/exceptions',
        name: 'operations-exceptions',
        component: ExceptionsPage,
        meta: { title: '异常列表', menuKey: '/operations' },
      },
      {
        path: 'operations/pending-actions',
        name: 'operations-pending-actions',
        component: PendingActionsPage,
        meta: { title: '待办事项', menuKey: '/operations' },
      },
      {
        path: 'operations/lifecycle',
        name: 'operations-lifecycle',
        component: LifecyclePage,
        meta: { title: '生命周期', menuKey: '/operations' },
      },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})
