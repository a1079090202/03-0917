<template>
  <div>
    <h1>出库销售</h1>
    <div class="page-sub">死规矩：同一药品先出效期最近的批，一批不够才动下一批；过期批、停售批系统直接拒</div>

    <div class="card">
      <div v-if="err" class="msg err">{{ err }}</div>
      <div v-if="result" class="msg ok">
        出库成功，单号 {{ result.order_no }}：
        <span v-for="(it, i) in result.items" :key="i">
          批号 {{ it.batch_no }}（效期 {{ it.expiry_date }}）×{{ it.quantity }}<span v-if="i < result.items.length - 1">；</span>
        </span>
      </div>

      <div class="form-grid">
        <label class="field">出库门店
          <select v-model.number="form.store_id" @change="loadBatches">
            <option v-for="s in stores" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <label class="field">药品
          <select v-model.number="form.drug_id" @change="loadBatches">
            <option :value="0" disabled>选择药品</option>
            <option v-for="d in drugs" :key="d.id" :value="d.id">{{ d.name }}（{{ d.spec }}）</option>
          </select>
        </label>
        <label class="field">数量（最小单位）
          <input type="number" min="1" step="1" v-model.number="form.quantity" style="width:120px" />
        </label>
        <label class="field">类型
          <select v-model="form.order_type">
            <option value="SALE">销售（整盒）</option>
            <option value="SPLIT_SALE">拆零销售（另记拆零台账）</option>
          </select>
        </label>
        <label class="field">经办人 <input v-model.trim="form.operator" placeholder="姓名" /></label>
      </div>

      <div class="toolbar mt">
        <button @click="preview" :disabled="!canQuery">预览效期优先分配</button>
        <label style="font-size:13px">
          <input type="checkbox" v-model="manual" @change="loadBatches" /> 手动指定批次（仍受效期先出校验）
        </label>
        <div class="spacer"></div>
        <button class="primary" :disabled="!canQuery || saving" @click="submit">{{ saving ? '提交中…' : '确认出库' }}</button>
      </div>

      <div v-if="previewRows.length" class="mt">
        <h2 style="font-size:14px">按效期最近优先，本单将出库：</h2>
        <table>
          <thead><tr><th>批号</th><th>有效期至</th><th class="num-cell">该批可售</th><th class="num-cell">本单出库</th></tr></thead>
          <tbody>
            <tr v-for="r in previewRows" :key="r.batch_id">
              <td>{{ r.batch_no }}</td><td>{{ r.expiry_date }}</td>
              <td class="num-cell">{{ r.available }}</td>
              <td class="num-cell"><b>{{ r.take }}</b></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="manual && batches.length" class="mt">
        <h2 style="font-size:14px">手动指定（合计须等于出库数量，且不得违反效期先出）：</h2>
        <table>
          <thead><tr><th>批号</th><th>有效期至</th><th>状态</th><th class="num-cell">可售/库存</th><th class="num-cell">指定出库</th></tr></thead>
          <tbody>
            <tr v-for="b in batches" :key="b.batch_id">
              <td>{{ b.batch_no }}</td><td>{{ b.expiry_date }}</td>
              <td>
                <span v-if="b.sellable" class="badge b-ok">可售</span>
                <span v-else class="badge b-bad">{{ b.block_reason }}</span>
              </td>
              <td class="num-cell">{{ b.available }}</td>
              <td class="num-cell">
                <input type="number" min="0" step="1" v-model.number="b._take" style="width:90px" :disabled="!b.sellable" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2>最近出库单</h2>
      <table>
        <thead><tr><th>出库单号</th><th>时间</th><th>类型</th><th>经办人</th><th>明细（批号 / 效期 / 数量）</th></tr></thead>
        <tbody>
          <tr v-for="o in recent" :key="o.id">
            <td>{{ o.order_no }}</td><td>{{ o.created_at }}</td>
            <td><span class="badge" :class="o.order_type === 'SPLIT_SALE' ? 'b-warn' : 'b-ok'">{{ ORDER_TYPE[o.order_type] }}</span></td>
            <td>{{ o.operator }}</td>
            <td>
              <div v-for="(it, i) in o.items" :key="i">
                {{ it.drug_name }} / {{ it.batch_no }} / {{ it.expiry_date }} / ×{{ it.quantity }}
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { ORDER_TYPE } from '../utils'

const stores = ref([])
const drugs = ref([])
const batches = ref([])
const previewRows = ref([])
const recent = ref([])
const manual = ref(false)
const err = ref('')
const result = ref(null)
const saving = ref(false)

const form = reactive({ store_id: 0, drug_id: 0, quantity: null, order_type: 'SALE', operator: '' })
const canQuery = computed(() => form.store_id && form.drug_id && form.quantity > 0)

async function loadBatches() {
  previewRows.value = []
  result.value = null
  if (!form.store_id || !form.drug_id) { batches.value = []; return }
  const rows = await api.get(`/api/drugs/${form.drug_id}/sellable-batches?store_id=${form.store_id}`)
  batches.value = rows.map(r => ({ ...r, _take: 0 }))
}

async function preview() {
  err.value = ''; result.value = null
  try {
    previewRows.value = await api.post('/api/outbound/preview', {
      store_id: form.store_id, drug_id: form.drug_id, quantity: form.quantity,
    })
  } catch (e) {
    previewRows.value = []
    err.value = e.message
  }
}

async function submit() {
  err.value = ''; result.value = null
  if (!form.operator) { err.value = '请填写经办人'; return }
  const item = { drug_id: form.drug_id, quantity: form.quantity }
  if (manual.value) {
    const allocations = batches.value.filter(b => b._take > 0).map(b => ({ batch_id: b.batch_id, quantity: b._take }))
    if (!allocations.length) { err.value = '手动模式下请至少指定一个批次的出库数量'; return }
    item.allocations = allocations
  }
  saving.value = true
  try {
    result.value = await api.post('/api/outbound', {
      store_id: form.store_id, order_type: form.order_type,
      operator: form.operator, items: [item],
    })
    previewRows.value = []
    await Promise.all([loadBatches(), loadRecent()])
  } catch (e) {
    err.value = e.message
  } finally {
    saving.value = false
  }
}

async function loadRecent() { recent.value = await api.get('/api/outbound?limit=10') }

onMounted(async () => {
  const [s, d] = await Promise.all([api.get('/api/stores'), api.get('/api/drugs')])
  stores.value = s
  drugs.value = d
  await loadRecent()
})
</script>
