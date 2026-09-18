<template>
  <div>
    <h1>质检管理</h1>
    <div class="page-sub">不合格整批停售；恢复必须挂质检放行单号，口头放行系统不认；过期锁死批谁也解不开</div>

    <div class="card">
      <h2>判定停售</h2>
      <div v-if="susErr" class="msg err">{{ susErr }}</div>
      <div v-if="susOk" class="msg ok">{{ susOk }}</div>
      <div class="form-grid">
        <label class="field" style="min-width:320px">批次（正常在售）
          <select v-model.number="sus.batch_id">
            <option :value="0" disabled>选择批次</option>
            <option v-for="b in normalBatches" :key="b.id" :value="b.id">
              {{ b.drug_name }} / {{ b.batch_no }} / 效期 {{ b.expiry_date }} / 存 {{ b.on_hand }}{{ b.unit }}
            </option>
          </select>
        </label>
        <label class="field" style="min-width:240px">停售原因 <input v-model.trim="sus.reason" placeholder="如：抽检可见异物" /></label>
        <label class="field">经办人 <input v-model.trim="sus.operator" /></label>
        <button class="danger" @click="doSuspend">判定停售</button>
      </div>
    </div>

    <div class="card">
      <h2>质检放行</h2>
      <div v-if="relErr" class="msg err">{{ relErr }}</div>
      <div v-if="relOk" class="msg ok">{{ relOk }}</div>
      <div class="form-grid">
        <label class="field" style="min-width:320px">停售中的批次
          <select v-model.number="rel.batch_id">
            <option :value="0" disabled>选择批次</option>
            <option v-for="b in suspendedBatches" :key="b.id" :value="b.id">
              {{ b.drug_name }} / {{ b.batch_no }} / {{ b.qc_reason || '停售中' }}
            </option>
          </select>
        </label>
        <label class="field" style="min-width:220px">质检放行单号 <input v-model.trim="rel.release_doc_no" placeholder="必填，如 QJ-FX-2026-001" /></label>
        <label class="field">经办人 <input v-model.trim="rel.operator" /></label>
        <button class="primary" @click="doRelease">凭单放行</button>
      </div>
    </div>

    <div class="card">
      <h2>质检记录</h2>
      <table>
        <thead><tr><th>时间</th><th>药品</th><th>批号</th><th>动作</th><th>原因 / 放行单号</th><th>经办人</th></tr></thead>
        <tbody>
          <tr v-for="r in records" :key="r.id">
            <td>{{ r.created_at }}</td><td>{{ r.drug_name }}</td><td>{{ r.batch_no }}</td>
            <td><span class="badge" :class="r.action === 'SUSPEND' ? 'b-bad' : 'b-ok'">{{ r.action === 'SUSPEND' ? '停售' : '放行' }}</span></td>
            <td>{{ r.action === 'SUSPEND' ? r.reason : r.release_doc_no }}</td>
            <td>{{ r.operator }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'

const normalBatches = ref([])
const suspendedBatches = ref([])
const records = ref([])
const sus = reactive({ batch_id: 0, reason: '', operator: '' })
const rel = reactive({ batch_id: 0, release_doc_no: '', operator: '' })
const susErr = ref(''); const susOk = ref('')
const relErr = ref(''); const relOk = ref('')

async function load() {
  const [normal, suspended, recs] = await Promise.all([
    api.get('/api/batches?status=NORMAL'),
    api.get('/api/batches?status=QC_SUSPENDED'),
    api.get('/api/qc-records'),
  ])
  normalBatches.value = normal.filter(b => b.on_hand > 0)
  suspendedBatches.value = suspended
  records.value = recs
}

async function doSuspend() {
  susErr.value = ''; susOk.value = ''
  if (!sus.batch_id || !sus.reason || !sus.operator) { susErr.value = '请选批次并填齐原因、经办人'; return }
  try {
    await api.post(`/api/batches/${sus.batch_id}/suspend`, sus)
    susOk.value = '已整批停售，立即禁止出库与调拨'
    sus.batch_id = 0; sus.reason = ''
    await load()
  } catch (e) { susErr.value = e.message }
}

async function doRelease() {
  relErr.value = ''; relOk.value = ''
  if (!rel.batch_id || !rel.operator) { relErr.value = '请选批次并填写经办人'; return }
  try {
    await api.post(`/api/batches/${rel.batch_id}/release`, rel)
    relOk.value = '已凭质检放行单恢复销售'
    rel.batch_id = 0; rel.release_doc_no = ''
    await load()
  } catch (e) { relErr.value = e.message }
}

onMounted(load)
</script>
