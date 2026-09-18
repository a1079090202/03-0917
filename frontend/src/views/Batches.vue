<template>
  <div>
    <h1>批次台账</h1>
    <div class="page-sub">每一批的状态、效期、在手量；近效期自动标黄，过期整批锁死</div>

    <div class="card">
      <div class="toolbar">
        <input v-model.trim="q" placeholder="搜批号 / 药品名" @input="load" style="width:200px" />
        <select v-model="status" @change="load">
          <option value="">全部状态</option>
          <option value="NORMAL">正常</option>
          <option value="QC_SUSPENDED">质检停售</option>
          <option value="EXPIRED_LOCKED">过期锁死</option>
        </select>
        <label style="font-size:13px"><input type="checkbox" v-model="nearOnly" @change="load" /> 只看近效期</label>
        <div class="spacer"></div>
        <span class="muted">{{ rows.length }} 个批次</span>
      </div>
      <table>
        <thead>
          <tr><th>药品</th><th>规格</th><th>批号</th><th>生产日期</th><th>有效期至</th><th class="num-cell">剩余天数</th><th>状态</th><th class="num-cell">在手库存</th><th>供应商</th></tr>
        </thead>
        <tbody>
          <tr v-for="b in rows" :key="b.id">
            <td>{{ b.drug_name }}</td><td>{{ b.spec }}</td><td>{{ b.batch_no }}</td>
            <td>{{ b.production_date }}</td><td>{{ b.expiry_date }}</td>
            <td class="num-cell">
              <span v-if="b.days_to_expiry < 0" class="badge b-bad">已过期 {{ -b.days_to_expiry }} 天</span>
              <span v-else-if="b.is_near_expiry" class="badge b-warn">{{ b.days_to_expiry }} 天</span>
              <span v-else>{{ b.days_to_expiry }} 天</span>
            </td>
            <td>
              <span class="badge" :class="BATCH_STATUS[b.status].cls">{{ BATCH_STATUS[b.status].text }}</span>
              <span v-if="b.is_near_expiry && b.status === 'NORMAL'" class="badge b-warn">近效期</span>
            </td>
            <td class="num-cell">{{ b.on_hand }} {{ b.unit }}</td>
            <td>{{ b.supplier }}</td>
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

const rows = ref([])
const q = ref('')
const status = ref('')
const nearOnly = ref(false)

async function load() {
  const params = new URLSearchParams()
  if (q.value) params.set('q', q.value)
  if (status.value) params.set('status', status.value)
  let data = await api.get('/api/batches?' + params.toString())
  if (nearOnly.value) data = data.filter(b => b.is_near_expiry)
  rows.value = data
}

onMounted(load)
</script>
