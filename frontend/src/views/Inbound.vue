<template>
  <div>
    <h1>入库登记</h1>
    <div class="page-sub">一批一条：批号、生产日期、有效期至、数量、供应商，少一样进不了账</div>

    <div class="card">
      <div v-if="err" class="msg err">{{ err }}</div>
      <div v-if="ok" class="msg ok">{{ ok }}</div>
      <div class="form-grid">
        <label class="field">收货地点
          <select v-model.number="form.store_id">
            <option v-for="s in stores" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <label class="field">经办人 <input v-model.trim="form.operator" placeholder="姓名" /></label>
        <label class="field">备注 <input v-model.trim="form.note" placeholder="选填" /></label>
      </div>

      <table class="mt">
        <thead>
          <tr><th>药品</th><th>批号</th><th>生产日期</th><th>有效期至</th><th>数量（最小单位）</th><th>供应商</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="(it, i) in form.items" :key="i">
            <td>
              <select v-model.number="it.drug_id">
                <option :value="0" disabled>选择药品</option>
                <option v-for="d in drugs" :key="d.id" :value="d.id">{{ d.name }}（{{ d.spec }}）</option>
              </select>
            </td>
            <td><input v-model.trim="it.batch_no" placeholder="批号" /></td>
            <td><input type="date" v-model="it.production_date" /></td>
            <td><input type="date" v-model="it.expiry_date" /></td>
            <td><input type="number" min="1" step="1" v-model.number="it.quantity" style="width:100px" /></td>
            <td><input v-model.trim="it.supplier" placeholder="供应商" /></td>
            <td><button class="small danger" @click="form.items.splice(i, 1)" :disabled="form.items.length === 1">删</button></td>
          </tr>
        </tbody>
      </table>
      <div class="mt toolbar">
        <button @click="addRow">+ 加一批</button>
        <div class="spacer"></div>
        <button class="primary" :disabled="saving" @click="submit">{{ saving ? '提交中…' : '登记入库' }}</button>
      </div>
    </div>

    <div class="card">
      <h2>最近入库单</h2>
      <table>
        <thead><tr><th>入库单号</th><th>时间</th><th>经办人</th><th>明细</th></tr></thead>
        <tbody>
          <tr v-for="o in recent" :key="o.id">
            <td>{{ o.order_no }}</td><td>{{ o.created_at }}</td><td>{{ o.operator }}</td>
            <td>
              <div v-for="(it, i) in o.items" :key="i">
                {{ it.drug_name }} / {{ it.batch_no }} / 效期 {{ it.expiry_date }} / ×{{ it.quantity }} / {{ it.supplier }}
              </div>
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

const stores = ref([])
const drugs = ref([])
const recent = ref([])
const err = ref('')
const ok = ref('')
const saving = ref(false)

const blank = () => ({ drug_id: 0, batch_no: '', production_date: '', expiry_date: '', quantity: null, supplier: '' })
const form = reactive({ store_id: 1, operator: '', note: '', items: [blank()] })

const addRow = () => form.items.push(blank())

async function loadRecent() { recent.value = await api.get('/api/inbound?limit=10') }

async function submit() {
  err.value = ''; ok.value = ''
  for (const it of form.items) {
    if (!it.drug_id || !it.batch_no || !it.production_date || !it.expiry_date || !it.quantity || !it.supplier) {
      err.value = '每批必须填齐：药品、批号、生产日期、有效期至、数量、供应商'
      return
    }
  }
  if (!form.operator) { err.value = '请填写经办人'; return }
  saving.value = true
  try {
    const r = await api.post('/api/inbound', form)
    ok.value = `入库成功，单号 ${r.order_no}`
    form.items = [blank()]
    await loadRecent()
  } catch (e) {
    err.value = e.message
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  const [s, d] = await Promise.all([api.get('/api/stores'), api.get('/api/drugs')])
  stores.value = s
  drugs.value = d
  form.store_id = (s.find(x => x.is_warehouse) || s[0]).id
  await loadRecent()
})
</script>
