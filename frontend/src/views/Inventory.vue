<template>
  <div>
    <h1>库存查询</h1>
    <div class="page-sub">按门店 / 药品查看各批次现存数量</div>

    <div class="card">
      <div class="toolbar">
        <select v-model.number="storeId" @change="load">
          <option :value="0">全部门店</option>
          <option v-for="s in stores" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <select v-model.number="drugId" @change="load">
          <option :value="0">全部药品</option>
          <option v-for="d in drugs" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
        <div class="spacer"></div>
        <span class="muted">{{ rows.length }} 条</span>
      </div>
      <table>
        <thead><tr><th>门店</th><th>药品</th><th>规格</th><th>批号</th><th>有效期至</th><th>状态</th><th class="num-cell">库存</th></tr></thead>
        <tbody>
          <tr v-for="(r, i) in rows" :key="i">
            <td>{{ r.store_name }}</td><td>{{ r.drug_name }}</td><td>{{ r.spec }}</td>
            <td>{{ r.batch_no }}</td><td>{{ r.expiry_date }}</td>
            <td>
              <span class="badge" :class="BATCH_STATUS[r.status].cls">{{ BATCH_STATUS[r.status].text }}</span>
              <span v-if="r.is_near_expiry && r.status === 'NORMAL'" class="badge b-warn">近效期</span>
            </td>
            <td class="num-cell"><b>{{ r.quantity }}</b> {{ r.unit }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { BATCH_STATUS } from '../utils'

const stores = ref([])
const drugs = ref([])
const rows = ref([])
const storeId = ref(0)
const drugId = ref(0)

async function load() {
  const params = new URLSearchParams()
  if (storeId.value) params.set('store_id', storeId.value)
  if (drugId.value) params.set('drug_id', drugId.value)
  rows.value = await api.get('/api/inventory?' + params.toString())
}

onMounted(async () => {
  const [s, d] = await Promise.all([api.get('/api/stores'), api.get('/api/drugs')])
  stores.value = s
  drugs.value = d
  await load()
})
</script>
