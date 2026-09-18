<template>
  <div>
    <h1>库存流水</h1>
    <div class="page-sub">每动一批必留一条：谁、什么时候、哪个店、哪批、动了多少、动后结存</div>

    <div class="card">
      <div class="toolbar">
        <select v-model.number="storeId" @change="load">
          <option :value="0">全部门店</option>
          <option v-for="s in stores" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <select v-model="changeType" @change="load">
          <option value="">全部类型</option>
          <option v-for="(label, key) in LEDGER_TYPE" :key="key" :value="key">{{ label }}</option>
        </select>
        <div class="spacer"></div>
        <span class="muted">最近 {{ rows.length }} 条</span>
      </div>
      <table>
        <thead><tr><th>时间</th><th>门店</th><th>药品</th><th>批号</th><th>类型</th><th class="num-cell">变动</th><th class="num-cell">动后结存</th><th>单号</th><th>经办人</th><th>备注</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.ts }}</td><td>{{ r.store_name }}</td><td>{{ r.drug_name }}</td><td>{{ r.batch_no }}</td>
            <td><span class="badge" :class="badgeCls(r)">{{ LEDGER_TYPE[r.change_type] || r.change_type }}</span></td>
            <td class="num-cell" :style="{ color: r.qty_change > 0 ? '#1a7f5a' : r.qty_change < 0 ? '#b91c1c' : '#6b7a73' }">
              {{ r.qty_change > 0 ? '+' + r.qty_change : r.qty_change }}
            </td>
            <td class="num-cell">{{ r.balance_after ?? '—' }}</td>
            <td>{{ r.ref_no || '—' }}</td><td>{{ r.operator }}</td><td class="muted">{{ r.note }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { LEDGER_TYPE } from '../utils'

const stores = ref([])
const rows = ref([])
const storeId = ref(0)
const changeType = ref('')

function badgeCls(r) {
  if (r.change_type === 'INBOUND' || r.change_type === 'TRANSFER_IN') return 'b-ok'
  if (r.change_type === 'EXPIRY_LOCK' || r.change_type === 'QC_SUSPEND') return 'b-bad'
  if (r.change_type === 'QC_RELEASE') return 'b-ok'
  return 'b-warn'
}

async function load() {
  const params = new URLSearchParams()
  if (storeId.value) params.set('store_id', storeId.value)
  if (changeType.value) params.set('change_type', changeType.value)
  rows.value = await api.get('/api/ledger?' + params.toString())
}

onMounted(async () => {
  stores.value = await api.get('/api/stores')
  await load()
})
</script>
