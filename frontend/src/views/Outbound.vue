<template>
  <div class="panel">
    <h2>出库（门店销售 / 拆零销售）</h2>
    <div class="rule-box">
      死规矩：同一药品系统按 <b>近效期先出（FEFO）</b> 自动分配批次，一批不够才动下一批，每动一批留一行流水。
      已过期批次当天锁死、质检停售批次一律不能出。整包装与拆零分开记账，不混一笔。
    </div>
    <div class="grid c4">
      <label class="fld">出库货位
        <select v-model="form.location_id">
          <option :value="null">请选择</option>
          <option v-for="l in locations" :key="l.id" :value="l.id">
            {{ l.kind === 'warehouse' ? '总仓' : l.name }}
          </option>
        </select>
      </label>
      <label class="fld">药品
        <select v-model="form.drug_id" @change="resetPreview">
          <option :value="null">请选择</option>
          <option v-for="d in drugs" :key="d.id" :value="d.id">
            {{ d.code }} {{ d.name }}（{{ d.spec }}）
          </option>
        </select>
      </label>
      <label class="fld">数量（最小包装单位整数）
        <input type="number" min="1" step="1" v-model.number="form.qty" @input="resetPreview" />
      </label>
      <label class="fld">出库类型
        <select v-model="form.kind">
          <option value="sale">整包装销售</option>
          <option value="split">拆零销售（另记拆零台账）</option>
        </select>
      </label>
      <label class="fld">经办人<input v-model="form.operator" /></label>
      <label class="fld">备注<input v-model="form.note" /></label>
    </div>

    <div style="margin-top:12px; display:flex; gap:10px; align-items:center; flex-wrap:wrap">
      <button class="btn gray" @click="preview">先看 FEFO 分配</button>
      <label class="fld" style="min-width:340px">
        指定批号出库（合规验收用：选非 FEFO 首选批/锁定批都会被拒）
        <select v-model="form.requested_batch_id">
          <option :value="null">系统自动 FEFO（默认）</option>
          <option v-for="b in candidateBatches" :key="b.id" :value="b.id">
            {{ b.batch_no }}（至 {{ b.expiry_date }}，存 {{ b.total_qty }}）
            <template v-if="b.flag === 'expired'">·已过期锁死</template>
            <template v-else-if="b.flag === 'hold'">·质检停售</template>
            <template v-else-if="b.flag === 'near'">·近效期</template>
          </option>
        </select>
      </label>
      <button class="btn" :disabled="busy || !canSubmit" @click="submit">
        {{ busy ? '提交中…' : '确认出库' }}
      </button>
    </div>

    <div v-if="previewData" class="alloc-box">
      <b>FEFO 预分配：</b>
      <table style="margin-top:6px">
        <thead><tr><th>顺序</th><th>批号</th><th>有效期至</th><th class="right">该批现存</th><th class="right">本次出库</th></tr></thead>
        <tbody>
          <tr v-for="(a, i) in previewData.allocations" :key="a.batch_id"
              :style="form.requested_batch_id && form.requested_batch_id !== previewData.allocations[0].batch_id && i === 0
                ? { background:'#fdf6ec' } : null">
            <td>{{ i + 1 }}{{ i === 0 ? '（必须先出）' : '' }}</td>
            <td><b>{{ a.batch_no }}</b></td><td>{{ a.expiry_date }}</td>
            <td class="right">{{ a.stock_qty }}</td><td class="right">{{ a.take }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="panel">
    <h2>最近出库流水（每单按批次展开）</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>出库单号</th><th>时间</th><th>货位</th><th>药品</th>
          <th>类型</th><th class="right">总数</th><th>批次明细</th><th>经办</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.no">
            <td>{{ r.no }}</td><td>{{ r.time }}</td><td>{{ r.location }}</td>
            <td>{{ r.drug_name }}</td>
            <td><span class="badge" :class="r.kind === 'split' ? 'hold' : 'normal'">
              {{ r.kind === 'split' ? '拆零' : '整包装' }}
            </span></td>
            <td class="right"><b>{{ r.qty }}</b> {{ r.unit }}</td>
            <td class="wrap">
              <details class="sub-flow">
                <summary>{{ r.flows.length }} 个批次</summary>
                <span v-for="f in r.flows" :key="f.batch_id" style="margin-right:14px">
                  {{ f.batch_no }}（至 {{ f.expiry_date }}）出 {{ f.qty }}
                </span>
              </details>
            </td>
            <td>{{ r.operator }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { toast } from '../toast'

const drugs = ref([])
const locations = ref([])
const rows = ref([])
const busy = ref(false)
const previewData = ref(null)
const form = ref({
  location_id: null, drug_id: null, qty: null, kind: 'sale',
  operator: '营业员', note: null, requested_batch_id: null,
})

const canSubmit = computed(() =>
  form.value.location_id && form.value.drug_id && form.value.qty > 0)

const candidateBatches = ref([])

async function loadCandidates() {
  candidateBatches.value = []
  if (form.value.location_id && form.value.drug_id) {
    const p = new URLSearchParams({
      location_id: form.value.location_id,
      drug_id: form.value.drug_id,
    })
    candidateBatches.value = await api.get(`/api/batches?${p}`)
  }
}

function resetPreview() {
  previewData.value = null
  form.value.requested_batch_id = null
  loadCandidates()
}

async function preview() {
  if (!canSubmit.value) return toast.err('请先选齐货位、药品和正整数数量')
  try {
    previewData.value = await api.post('/api/outbound/preview', {
      drug_id: form.value.drug_id,
      location_id: form.value.location_id,
      qty: form.value.qty,
    })
  } catch (e) { previewData.value = null; toast.err(e) }
}

async function submit() {
  busy.value = true
  try {
    const r = await api.post('/api/outbound', { ...form.value })
    toast.ok(`出库成功，单号 ${r.no}`)
    form.value.qty = null
    form.value.requested_batch_id = null
    previewData.value = null
    await loadRows()
  } catch (e) { toast.err(e) } finally { busy.value = false }
}

async function loadRows() { rows.value = await api.get('/api/ledger/outbound?limit=100') }

onMounted(async () => {
  drugs.value = await api.get('/api/drugs')
  locations.value = await api.get('/api/locations')
  await loadRows()
})
</script>
