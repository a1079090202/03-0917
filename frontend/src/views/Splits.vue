<template>
  <div>
    <h1>拆零台账</h1>
    <div class="page-sub">拆零销售单独记账，不与整盒销售混一笔</div>

    <div class="card">
      <div class="toolbar">
        <select v-model.number="storeId" @change="load">
          <option :value="0">全部门店</option>
          <option v-for="s in stores" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <div class="spacer"></div>
        <span class="muted">{{ rows.length }} 条</span>
      </div>
      <table>
        <thead><tr><th>时间</th><th>门店</th><th>药品</th><th>规格</th><th>批号</th><th>效期</th><th class="num-cell">拆零数量</th><th>经办人</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.ts }}</td><td>{{ r.store_name }}</td><td>{{ r.drug_name }}</td><td>{{ r.spec }}</td>
            <td>{{ r.batch_no }}</td><td>{{ r.expiry_date }}</td>
            <td class="num-cell"><b>{{ r.quantity }}</b> {{ r.unit }}</td><td>{{ r.operator }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!rows.length" class="muted">暂无拆零记录</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const stores = ref([])
const rows = ref([])
const storeId = ref(0)

async function load() {
  const params = storeId.value ? `?store_id=${storeId.value}` : ''
  rows.value = await api.get('/api/split-records' + params)
}

onMounted(async () => {
  stores.value = await api.get('/api/stores')
  await load()
})
</script>
