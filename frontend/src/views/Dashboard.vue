<template>
  <div class="panel">
    <h2>批次台账（按效期排序）</h2>
    <div class="toolbar">
      <label class="fld">药品
        <select v-model="drugId" @change="load">
          <option :value="null">全部药品</option>
          <option v-for="d in drugs" :key="d.id" :value="d.id">{{ d.code }} {{ d.name }}</option>
        </select>
      </label>
      <label class="fld">货位
        <select v-model="locationId" @change="load">
          <option :value="null">总仓+全部门店</option>
          <option v-for="l in locations" :key="l.id" :value="l.id">
            {{ l.kind === 'warehouse' ? '总仓' : l.name }}
          </option>
        </select>
      </label>
      <label class="fld">效期状态
        <select v-model="flag">
          <option :value="null">全部</option>
          <option value="normal">正常</option>
          <option value="near">近效期（≤6个月）</option>
          <option value="expired">已过期（锁死）</option>
          <option value="hold">质检停售</option>
        </select>
      </label>
      <button class="btn sm gray" @click="load">刷新</button>
      <span class="spacer"></span>
      <span class="muted">数量单位均为最小包装单位（支/片/粒/瓶/袋/丸）</span>
    </div>

    <div class="grid c4" style="margin-bottom:14px">
      <div class="stat"><div class="n">{{ stats.normal }}</div><div class="l">正常批次</div></div>
      <div class="stat warn"><div class="n">{{ stats.near }}</div><div class="l">近效期批次（6个月内）</div></div>
      <div class="stat danger"><div class="n">{{ stats.expired }}</div><div class="l">已过期锁死批次</div></div>
      <div class="stat" style="--primary-dark:#7b3f8f"><div class="n" style="color:#7b3f8f">{{ stats.hold }}</div><div class="l">质检停售批次</div></div>
    </div>

    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>药品</th><th>规格</th><th>批号</th><th>生产日期</th><th>有效期至</th>
            <th>状态</th><th class="right">库存合计</th><th>单位</th><th>供应商</th><th>库存分布</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in filtered" :key="b.id" :style="rowStyle(b)">
            <td class="wrap">{{ b.drug_code }} {{ b.drug_name }}</td>
            <td class="wrap">{{ b.spec }}</td>
            <td><b>{{ b.batch_no }}</b></td>
            <td>{{ b.production_date }}</td>
            <td>{{ b.expiry_date }}</td>
            <td><span class="badge" :class="b.flag">{{ flagText(b.flag) }}</span></td>
            <td class="right"><b>{{ b.total_qty }}</b></td>
            <td>{{ b.unit }}</td>
            <td class="wrap">{{ b.supplier }}</td>
            <td class="wrap">
              <span v-for="d in b.distribution" :key="d.location_id" class="muted" style="margin-right:10px">
                {{ d.location_name }} {{ d.qty }}
              </span>
              <span v-if="!b.distribution.length" class="muted">无库存</span>
            </td>
          </tr>
          <tr v-if="!filtered.length"><td colspan="10" class="center muted" style="padding:24px">无符合条件的批次</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const drugs = ref([])
const locations = ref([])
const drugId = ref(null)
const locationId = ref(null)
const flag = ref(null)

const flagText = { normal: '正常', near: '近效期', expired: '已过期·锁死', hold: '停售' }
const rowStyle = (b) => b.flag === 'expired'
  ? { background: '#fff5f4' }
  : b.flag === 'near' ? { background: '#fffcf5' } : null

const stats = computed(() => {
  const s = { normal: 0, near: 0, expired: 0, hold: 0 }
  for (const b of allCache.value) s[b.flag]++
  return s
})
const allCache = ref([])

const filtered = computed(() =>
  flag.value ? allCache.value.filter((b) => b.flag === flag.value) : allCache.value
)

async function load() {
  const p = new URLSearchParams()
  if (drugId.value) p.set('drug_id', drugId.value)
  if (locationId.value) p.set('location_id', locationId.value)
  allCache.value = await api.get(`/api/batches?${p}`)
}

onMounted(async () => {
  drugs.value = await api.get('/api/drugs')
  locations.value = await api.get('/api/locations')
  await load()
})
</script>
