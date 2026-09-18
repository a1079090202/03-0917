<template>
  <div>
    <h1>调拨管理</h1>
    <div class="page-sub">门店/总仓之间移库全程留痕：发出即扣库存，收货才入对方账，在途单独可查</div>

    <div class="card">
      <h2>新建调拨单</h2>
      <div v-if="err" class="msg err">{{ err }}</div>
      <div v-if="ok" class="msg ok">{{ ok }}</div>
      <div class="form-grid">
        <label class="field">调出
          <select v-model.number="form.from_store_id" @change="loadStock">
            <option v-for="s in stores" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <label class="field">调入
          <select v-model.number="form.to_store_id">
            <option v-for="s in stores" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <label class="field">批次（调出方可调库存）
          <select v-model.number="form.batch_id">
            <option :value="0" disabled>选择批次</option>
            <option v-for="b in stock" :key="b.batch_id" :value="b.batch_id">
              {{ b.drug_name }} / {{ b.batch_no }} / 效期 {{ b.expiry_date }} / 存 {{ b.quantity }}{{ b.unit }}
            </option>
          </select>
        </label>
        <label class="field">数量 <input type="number" min="1" step="1" v-model.number="form.quantity" style="width:100px" /></label>
        <label class="field">经办人 <input v-model.trim="form.operator" placeholder="姓名" /></label>
        <button class="primary" :disabled="saving" @click="submit">发出调拨</button>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <h2 style="margin:0">调拨单</h2>
        <select v-model="statusFilter" @change="load">
          <option value="">全部状态</option>
          <option value="IN_TRANSIT">在途</option>
          <option value="RECEIVED">已收货</option>
        </select>
      </div>
      <div v-if="recvErr" class="msg err">{{ recvErr }}</div>
      <table>
        <thead>
          <tr><th>单号</th><th>药品</th><th>批号</th><th>效期</th><th>调出</th><th>调入</th><th class="num-cell">数量</th><th>状态</th><th>发货</th><th>收货</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="t in list" :key="t.id">
            <td>{{ t.transfer_no }}</td><td>{{ t.drug_name }}</td><td>{{ t.batch_no }}</td><td>{{ t.expiry_date }}</td>
            <td>{{ t.from_store }}</td><td>{{ t.to_store }}</td>
            <td class="num-cell">{{ t.quantity }}</td>
            <td><span class="badge" :class="TRANSFER_STATUS[t.status].cls">{{ TRANSFER_STATUS[t.status].text }}</span></td>
            <td>{{ t.created_at }}<br /><span class="muted">{{ t.operator }}</span></td>
            <td>
              <template v-if="t.received_at">{{ t.received_at }}<br /><span class="muted">{{ t.received_by }}</span></template>
              <span v-else class="muted">—</span>
            </td>
            <td>
              <button v-if="t.status === 'IN_TRANSIT'" class="small primary" @click="receive(t)">收货入库</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { TRANSFER_STATUS } from '../utils'

const stores = ref([])
const stock = ref([])
const list = ref([])
const err = ref('')
const ok = ref('')
const recvErr = ref('')
const saving = ref(false)
const statusFilter = ref('')
const form = reactive({ from_store_id: 1, to_store_id: 2, batch_id: 0, quantity: null, operator: '' })

async function loadStock() {
  form.batch_id = 0
  if (!form.from_store_id) { stock.value = []; return }
  const rows = await api.get(`/api/inventory?store_id=${form.from_store_id}`)
  stock.value = rows.filter(r => r.status === 'NORMAL' && !r.is_expired)
}

async function load() {
  const params = statusFilter.value ? `?status=${statusFilter.value}` : ''
  list.value = await api.get('/api/transfers' + params)
}

async function submit() {
  err.value = ''; ok.value = ''
  if (form.from_store_id === form.to_store_id) { err.value = '调出与调入不能相同'; return }
  if (!form.batch_id || !form.quantity || !form.operator) { err.value = '请选批次并填齐数量、经办人'; return }
  saving.value = true
  try {
    const r = await api.post('/api/transfers', form)
    ok.value = `调拨单 ${r.transfer_no} 已发出（在途）`
    form.batch_id = 0; form.quantity = null
    await Promise.all([loadStock(), load()])
  } catch (e) {
    err.value = e.message
  } finally {
    saving.value = false
  }
}

async function receive(t) {
  recvErr.value = ''
  const operator = window.prompt(`确认收货 ${t.drug_name} / ${t.batch_no} ×${t.quantity}？请输入收货人姓名：`, '')
  if (!operator) return
  try {
    await api.post(`/api/transfers/${t.id}/receive`, { operator })
    await Promise.all([loadStock(), load()])
  } catch (e) {
    recvErr.value = e.message
  }
}

onMounted(async () => {
  stores.value = await api.get('/api/stores')
  if (stores.value.length > 1) {
    form.from_store_id = stores.value[0].id
    form.to_store_id = stores.value[1].id
  }
  await Promise.all([loadStock(), load()])
})
</script>
