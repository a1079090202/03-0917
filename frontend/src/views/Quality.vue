<template>
  <div class="panel">
    <h2>质检：不合格整批停售 / 凭放行单恢复</h2>
    <div class="rule-box">
      判不合格 → 整批停售，出库/调拨立即拦截；恢复销售必须登记<b>质检放行单编号</b>，
      口头放行不入账。注意：放行只解除停售标记，<b>已过有效期的批次仍然锁死</b>，谁也解不开。
    </div>

    <div class="grid c3">
      <label class="fld">选择批次
        <select v-model="batchId">
          <option :value="null">请选择</option>
          <option v-for="b in batches" :key="b.id" :value="b.id">
            {{ b.drug_name }}｜批号 {{ b.batch_no }}｜效期至 {{ b.expiry_date }}
            ｜{{ b.quality_status === 'hold' ? '停售中' : '正常' }}
          </option>
        </select>
      </label>
      <label class="fld">判定原因 / 说明
        <input v-model="reason" placeholder="如：抽检溶出度不合格" />
      </label>
      <label class="fld">经办人<input v-model="operator" /></label>
    </div>

    <div style="margin-top:12px; display:flex; gap:10px; align-items:center; flex-wrap:wrap">
      <button class="btn danger" :disabled="busy" @click="hold">判不合格·整批停售</button>
      <span style="width:1px;height:28px;background:var(--line)"></span>
      <label class="fld" style="min-width:240px">
        放行单号 <b>*</b>
        <input v-model="docNo" placeholder="如：FXD-2026-0918-03" />
      </label>
      <button class="btn" :disabled="busy" @click="release">凭放行单恢复销售</button>
    </div>
  </div>

  <div class="panel">
    <h2>质检动作台账</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>单号</th><th>时间</th><th>药品</th><th>批号</th>
          <th>动作</th><th>放行单号</th><th>原因</th><th>经办</th>
        </tr></thead>
        <tbody>
          <tr v-for="q in rows" :key="q.no">
            <td>{{ q.no }}</td><td>{{ q.time }}</td><td>{{ q.drug_name }}</td>
            <td><b>{{ q.batch_no }}</b></td>
            <td>
              <span class="badge" :class="q.action === 'hold' ? 'hold' : 'normal'">
                {{ q.action === 'hold' ? '停售' : '放行' }}
              </span>
            </td>
            <td>{{ q.doc_no || '—' }}</td><td class="wrap">{{ q.reason }}</td>
            <td>{{ q.operator }}</td>
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

const batches = ref([])
const rows = ref([])
const batchId = ref(null)
const reason = ref('')
const docNo = ref('')
const operator = ref('质检员')
const busy = ref(false)

async function loadBatches() { batches.value = await api.get('/api/batches?only_stock=true') }
async function loadRows() { rows.value = await api.get('/api/ledger/quality') }

async function hold() {
  if (!batchId.value) return toast.err('请先选择批次')
  if (!reason.value.trim()) return toast.err('停售必须填写判定原因')
  busy.value = true
  try {
    const r = await api.post('/api/quality/hold', {
      batch_id: batchId.value, reason: reason.value.trim(), operator: operator.value,
    })
    toast.ok(`已停售，单号 ${r.no}。该批即刻不能出库/调拨`)
    reason.value = ''
    await loadBatches(); await loadRows()
  } catch (e) { toast.err(e) } finally { busy.value = false }
}

async function release() {
  if (!batchId.value) return toast.err('请先选择批次')
  if (!docNo.value.trim()) return toast.err('放行必须挂质检放行单编号，口头放行不算')
  busy.value = true
  try {
    const r = await api.post('/api/quality/release', {
      batch_id: batchId.value, doc_no: docNo.value.trim(),
      reason: reason.value.trim() || null, operator: operator.value,
    })
    toast.ok(r.note ? `已凭单放行（${r.no}）。${r.note}` : `已凭单放行，单号 ${r.no}`)
    docNo.value = ''; reason.value = ''
    await loadBatches(); await loadRows()
  } catch (e) { toast.err(e) } finally { busy.value = false }
}

onMounted(async () => { await loadBatches(); await loadRows() })
</script>
