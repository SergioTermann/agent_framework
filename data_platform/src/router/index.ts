/**
 * 路由配置
 * 定义了地图页面和监控页面的路由
 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

// 定义路由
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Map',
    component: () => import('@/pages/MapView.vue'),
    meta: { title: '风场地图' }
  },
  {
    path: '/monitor',
    name: 'Monitor',
    component: () => import('@/pages/MonitorView.vue'),
    meta: { title: '风机监控' }
  },
  {
    path: '/video-analysis',
    name: 'VideoAnalysis',
    component: () => import('@/pages/VideoAnalysisView.vue'),
    meta: { title: 'AI视频分析' }
  }
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 路由守卫 - 设置页面标题
router.beforeEach((to, from, next) => {
  if (to.meta.title) {
    document.title = `${to.meta.title} - 风起时域科技有限公司AI故障定位系统`
  }
  next()
})

export default router

