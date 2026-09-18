import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', component: () => import('./views/Dashboard.vue'), meta: { title: '总览' } },
  { path: '/inbound', component: () => import('./views/Inbound.vue'), meta: { title: '入库登记' } },
  { path: '/outbound', component: () => import('./views/Outbound.vue'), meta: { title: '出库销售' } },
  { path: '/batches', component: () => import('./views/Batches.vue'), meta: { title: '批次台账' } },
  { path: '/inventory', component: () => import('./views/Inventory.vue'), meta: { title: '库存查询' } },
  { path: '/transfers', component: () => import('./views/Transfers.vue'), meta: { title: '调拨管理' } },
  { path: '/recall', component: () => import('./views/Recall.vue'), meta: { title: '召回追溯' } },
  { path: '/qc', component: () => import('./views/Qc.vue'), meta: { title: '质检管理' } },
  { path: '/splits', component: () => import('./views/Splits.vue'), meta: { title: '拆零台账' } },
  { path: '/reports', component: () => import('./views/Reports.vue'), meta: { title: '月度报表' } },
  { path: '/ledger', component: () => import('./views/Ledger.vue'), meta: { title: '库存流水' } },
  { path: '/drugs', component: () => import('./views/Drugs.vue'), meta: { title: '药品目录' } },
]

export default createRouter({
  // hash 模式：静态托管下刷新任意页面都不会 404
  history: createWebHashHistory(),
  routes,
})
