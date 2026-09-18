<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-name">批号效期台账</div>
        <div class="brand-sub">连锁药房 · 总仓/门店共用</div>
      </div>
      <nav>
        <RouterLink v-for="r in nav" :key="r.path" :to="r.path" v-slot="{ isActive }">
          <span class="nav-item" :class="{ active: isActive }">{{ r.title }}</span>
        </RouterLink>
      </nav>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
const nav = [
  { path: '/', title: '总览' },
  { path: '/inbound', title: '入库登记' },
  { path: '/outbound', title: '出库销售' },
  { path: '/batches', title: '批次台账' },
  { path: '/inventory', title: '库存查询' },
  { path: '/transfers', title: '调拨管理' },
  { path: '/recall', title: '召回追溯' },
  { path: '/qc', title: '质检管理' },
  { path: '/splits', title: '拆零台账' },
  { path: '/reports', title: '月度报表' },
  { path: '/ledger', title: '库存流水' },
  { path: '/drugs', title: '药品目录' },
]
</script>
