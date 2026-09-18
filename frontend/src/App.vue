<template>
  <header class="topbar">
    <h1>批号效期台账</h1>
    <span class="sub">总仓 + 8 门店 · 近效期先出 · 批次全程留痕</span>
    <nav class="tabs">
      <button v-for="t in tabs" :key="t.key"
              :class="{ active: tab === t.key }"
              @click="tab = t.key">{{ t.label }}</button>
    </nav>
  </header>

  <main>
    <Dashboard v-if="tab === 'dashboard'" />
    <Inbound v-else-if="tab === 'inbound'" />
    <Outbound v-else-if="tab === 'outbound'" />
    <TransferView v-else-if="tab === 'transfer'" />
    <QualityView v-else-if="tab === 'quality'" />
    <RecallView v-else-if="tab === 'recall'" />
    <ReportsView v-else-if="tab === 'reports'" />
    <Ledgers v-else-if="tab === 'ledgers'" />
  </main>

  <div v-if="msg" class="toast" :class="msg.type" @click="msg = null">{{ msg.text }}</div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import { toast } from './toast'
import Dashboard from './views/Dashboard.vue'
import Inbound from './views/Inbound.vue'
import Outbound from './views/Outbound.vue'
import TransferView from './views/Transfer.vue'
import QualityView from './views/Quality.vue'
import RecallView from './views/Recall.vue'
import ReportsView from './views/Reports.vue'
import Ledgers from './views/Ledgers.vue'

const tabs = [
  { key: 'dashboard', label: '批次台账' },
  { key: 'inbound', label: '入库' },
  { key: 'outbound', label: '出库' },
  { key: 'transfer', label: '门店调拨' },
  { key: 'quality', label: '质检停售/放行' },
  { key: 'recall', label: '召回追溯' },
  { key: 'reports', label: '月度报表' },
  { key: 'ledgers', label: '流水台账' },
]
const tab = ref(location.hash.replace('#', '') || 'dashboard')
window.addEventListener('hashchange', () => {
  const t = location.hash.replace('#', '')
  if (t) tab.value = t
})

const msg = ref(null)
let timer = null
toast.bind((type, text) => {
  msg.value = { type, text }
  clearTimeout(timer)
  timer = setTimeout(() => (msg.value = null), 5000)
})
onUnmounted(() => clearTimeout(timer))
</script>
