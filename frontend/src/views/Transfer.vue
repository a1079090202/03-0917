<template>
  <div class="panel">
    <h2>门店调拨（系统留痕，按 FEFO 拆批）</h2>
    <div class="rule-box">
      调拨同样强制近效期先出；发货后货进入"在途"，调入方点收货才入账。
      过期/停售批次不能发出；在途量在召回追溯中逐单列出。
    </div>
    <div class="grid c4">
      <label class="fld">调出货位
        <select v-model="form.from_location_id">
          <option :value="null">请选择</option>
          <option v-for="l in locations" :key="l.id" :value="l.id">
            {{ l.kind === 'warehouse' ? '总仓' : l.name }}
          </option>
        </select>
      </label>
      <label class="fld">调入货位
        <select v-model="form.to_location_id">
          <option :value="null">请选择</option>
          <option v-for="l in locations" :key="l.id" :value="l.id">
            {{ l.kind === 'warehouse' ? '总仓' : l.name }}
          </option>
        </select>
      </label>
      <label class="fld">药品
        <select v-model="form.drug_id">
          <option :value="null">请选择</option>
          <option v-for="d in drugs" :key="d.id" :value="d.id">
            {{ d.code }} {{ d.name }}（{{ d.spec }}）
          </option>
        </select>
      </label>
      <label class="fld">数量（最小包装单位整数）
        <input type="number" min="1" step="1" v-model.number="form.qty" />
      </label>
      <label class="fld">经办人<input v-model="form.operator" /></label>
    </div>
    <div style="margin-top:12px">
      <button class="btn" :disabled="busy" @click="ship">{{ busy ? '提交中…' : '发货（进入在途）' }}</button>
    </div>
  </div>

  <div class="panel">
    <h2>调拨单（在途单可收货）</h2>
    <div class="toolbar">
      <button class="btn sm gray" @click="load">刷新</button>
      <span class="muted">在途单重复点收货不会重复入账（条件状态更新抢占）</span>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>调拨单号</th><th>发货时间</th><th>药品</th>
          <th>调出 → 调入</th><th class="right">数量</th><th>批次明细</th>
          <th>状态</th><th>收货时间</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="t in rows" :key="t.no">
            <td>{{ t.no }}</td><td>{{ t.shipped_at }}</td><td>{{ t.drug_name }}</td>
            <td>{{ t.from }} → <b>{{ t.to }}</b></td>
            <td class="right">{{ t.qty }} {{ t.unit }}</td>
            <td class="wrap">
              <details class="sub-flow">
                <summary>{{ t.items.length }} 个批次</summary>
                <span v-for="i in t.items" :key="i.batch_no" style="margin-right:14px">
                  {{ i.batch_no }}（至 {{ i.expiry_date }}）{{ i.qty }}
                </span>
              </details>
            </td>
            <td>
              <span class="badge" :class="t.status === 'in_transit' ? 'transit' : 'done'">
                {{ t.status === 'in_transit' ? '在途' : '已收货' }}
              </span>
            </td>
            <td>{{ t.received_at || '—' }}</td>
            <td>
              <button v-if="t.status === 'in_transit'" class="btn sm"
                      @click="receive(t.id)">确认收货</button>
              <span v-else class="muted">完成</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { toast } from '../toast'

const drugs = ref([])
const locations = ref([])
const rows = ref([])
const busy = ref(false)
const form = ref({
  from_location_id: null, to_location_id: null, drug_id: null,
  qty: null, operator: '仓管员',
})

async function load() { rows.value = await api.get('/api/ledger/transfers?limit=200') }

async function ship() {
  const f = form.value
  if (!f.from_location_id || !f.to_location_id) return toast.err('请选择调出/调入货位')
  if (f.from_location_id === f.to_location_id) return toast.err('调出与调入不能是同一货位')
  if (!f.drug_id) return toast.err('请选择药品')
  if (!f.qty || f.qty <= 0 || !Number.isInteger(f.qty)) return toast.err('数量必须是正整数')
  busy.value = true
  try {
    const r = await api.post('/api/transfers', { ...f })
    toast.ok(`调拨单 ${r.no} 已发货，当前在途，待调入方确认收货`)
    f.qty = null
    await load()
  } catch (e) { toast.err(e) } finally { busy.value = false }
}

async function receive(id) {
  try {
    const r = await api.post(`/api/transfers/${id}/receive`, {})
    toast.ok(`调拨单 ${r.no} 已收货入账`)
    await load()
  } catch (e) { toast.err(e) }
}

onMounted(async () => {
  drugs.value = await api.get('/api/drugs')
  locations.value = await api.get('/api/locations')
  await load()
})
</script>
