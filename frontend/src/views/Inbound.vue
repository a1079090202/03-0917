<template>
  <div class="panel">
    <h2>入库登记</h2>
    <div class="rule-box">
      入库铁律：批号、生产日期、有效期至、数量、供应商五样缺一不进账；
      数量按最小包装单位填整数。同药品同批号再次入库，生产日期/有效期必须与台账一致。
    </div>
    <div class="grid c4">
      <label class="fld">药品 <b>*</b>
        <select v-model="form.drug_id">
          <option :value="null">请选择药品</option>
          <option v-for="d in drugs" :key="d.id" :value="d.id">
            {{ d.code }} {{ d.name }}（{{ d.spec }}）
          </option>
        </select>
      </label>
      <label class="fld">批号 <b>*</b>
        <input v-model="form.batch_no" placeholder="厂家批号" />
      </label>
      <label class="fld">生产日期 <b>*</b>
        <input type="date" v-model="form.production_date" />
      </label>
      <label class="fld">有效期至 <b>*</b>
        <input type="date" v-model="form.expiry_date" />
      </label>
      <label class="fld">数量（最小包装单位，整数）<b>*</b>
        <input type="number" min="1" step="1" v-model.number="form.qty" placeholder="如 200" />
      </label>
      <label class="fld">供应商 <b>*</b>
        <input v-model="form.supplier" placeholder="供应商全称" />
      </label>
      <label class="fld">经办人
        <input v-model="form.operator" />
      </label>
      <label class="fld">备注
        <input v-model="form.note" />
      </label>
    </div>
    <div style="margin-top:14px">
      <button class="btn" :disabled="busy" @click="submit">{{ busy ? '提交中…' : '确认入库' }}</button>
    </div>
  </div>

  <div class="panel">
    <h2>最近入库流水</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>入库单号</th><th>时间</th><th>药品</th><th>批号</th>
          <th>生产日期</th><th>有效期至</th><th class="right">数量</th><th>供应商</th><th>经办</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.no">
            <td>{{ r.no }}</td><td>{{ r.time }}</td><td>{{ r.drug_name }}</td>
            <td><b>{{ r.batch_no }}</b></td><td>{{ r.production_date }}</td>
            <td>{{ r.expiry_date }}</td><td class="right">{{ r.qty }} {{ r.unit }}</td>
            <td>{{ r.supplier }}</td><td>{{ r.operator }}</td>
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
const rows = ref([])
const busy = ref(false)
const form = ref({
  drug_id: null, batch_no: '', production_date: '', expiry_date: '',
  qty: null, supplier: '', operator: '仓管员', note: null,
})

async function loadRows() { rows.value = await api.get('/api/ledger/inbound?limit=100') }

async function submit() {
  const f = form.value
  if (!f.drug_id) return toast.err('请选择药品')
  if (!f.batch_no.trim()) return toast.err('批号不能为空')
  if (!f.production_date) return toast.err('生产日期不能为空')
  if (!f.expiry_date) return toast.err('有效期至不能为空')
  if (!f.qty || f.qty <= 0 || !Number.isInteger(f.qty)) return toast.err('数量必须是正整数（最小包装单位）')
  if (f.expiry_date <= f.production_date) return toast.err('有效期至必须晚于生产日期')
  if (!f.supplier.trim()) return toast.err('供应商不能为空')

  busy.value = true
  try {
    const r = await api.post('/api/inbound', { ...f, batch_no: f.batch_no.trim(), supplier: f.supplier.trim() })
    toast.ok(`入库成功，单号 ${r.no}；总仓该批现存 ${r.warehouse_qty}`)
    form.value = { drug_id: f.drug_id, batch_no: '', production_date: '', expiry_date: '',
                   qty: null, supplier: '', operator: '仓管员', note: null }
    await loadRows()
  } catch (e) { toast.err(e) } finally { busy.value = false }
}

onMounted(async () => {
  drugs.value = await api.get('/api/drugs')
  await loadRows()
})
</script>
