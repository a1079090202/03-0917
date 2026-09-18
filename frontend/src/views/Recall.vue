<template>
  <div class="panel">
    <h2>厂家召回追溯</h2>
    <div class="rule-box">
      输入厂家召回批号，系统一口气列出：发过哪些门店、各家收了多少、卖了多少（含拆零）、
      还剩多少、调出多少、调拨途中压在哪张单。下方恒等式必须为 0（总入库 = 总销售 + 现存 + 在途）。
    </div>
    <div class="toolbar">
      <label class="fld" style="min-width:260px">召回批号
        <input v-model="batchNo" placeholder="如：HG20260418" @keyup.enter="trace" />
      </label>
      <label class="fld" style="min-width:240px">药品（同名批号防串，可选）
        <select v-model="drugId">
          <option :value="null">不指定</option>
          <option v-for="d in drugs" :key="d.id" :value="d.id">{{ d.code }} {{ d.name }}</option>
        </select>
      </label>
      <button class="btn" :disabled="busy" @click="trace">{{ busy ? '查询中…' : '开始追溯' }}</button>
    </div>
  </div>

  <template v-if="data">
    <div class="panel">
      <h2>召回批次信息</h2>
      <div class="grid c4">
        <div class="stat"><div class="l">药品</div><div style="font-weight:600;margin-top:4px">
          {{ data.batch.drug_code }} {{ data.batch.drug_name }}</div></div>
        <div class="stat"><div class="l">批号</div><div style="font-weight:700;font-size:18px;margin-top:4px">
          {{ data.batch.batch_no }}</div></div>
        <div class="stat"><div class="l">有效期至</div><div style="margin-top:4px">{{ data.batch.expiry_date }}</div></div>
        <div class="stat"><div class="l">厂家 / 供应商</div><div style="margin-top:4px" class="wrap">
          {{ data.batch.manufacturer }}<br><span class="muted">{{ data.batch.supplier }}</span></div></div>
      </div>

      <h3>总量核对</h3>
      <div class="grid c4">
        <div class="stat"><div class="n">{{ data.summary.total_received }}</div><div class="l">总入库量</div></div>
        <div class="stat"><div class="n">{{ data.summary.total_sold }}</div><div class="l">总销售量（含拆零）</div></div>
        <div class="stat"><div class="n">{{ data.summary.total_current }}</div><div class="l">当前库存合计</div></div>
        <div class="stat" :class="data.summary.total_in_transit ? 'warn' : ''">
          <div class="n">{{ data.summary.total_in_transit }}</div><div class="l">调拨在途合计</div></div>
      </div>
      <div :class="data.summary.balance_check === 0 ? 'rule-box' : 'rule-box'"
           :style="data.summary.balance_check === 0
             ? { background:'#edf7f0', borderColor:'#9ccfae' }
             : { background:'#fdecea', borderColor:'#e0928a' }">
        账实平衡校验：总入库 − 总销售 − 现存 − 在途 =
        <b :style="{ color: data.summary.balance_check === 0 ? 'var(--ok)' : 'var(--danger)' }">
          {{ data.summary.balance_check }}</b>
        {{ data.summary.balance_check === 0 ? '（账平，可与纸面流向逐家对账）' : '（账不平，立即停查！）' }}
      </div>
    </div>

    <div class="panel">
      <h2>各门店/总仓流向（{{ data.locations.length }} 家全列，未涉及标 0）</h2>
      <div class="tbl-wrap">
        <table>
          <thead><tr>
            <th>货位</th><th class="right">收到量</th><th class="right">销售量(含拆零)</th>
            <th class="right">调出量</th><th class="right">当前剩余</th><th>备注</th>
          </tr></thead>
          <tbody>
            <tr v-for="l in data.locations" :key="l.location_id"
                :style="!l.touched ? { color: '#9aa4ad' } : null">
              <td>{{ l.kind === 'warehouse' ? '【总仓】' : '' }}{{ l.location_name }}</td>
              <td class="right">{{ l.received_qty }}</td>
              <td class="right">{{ l.sold_qty }}</td>
              <td class="right">{{ l.shipped_out_qty }}</td>
              <td class="right"><b>{{ l.current_qty }}</b></td>
              <td>{{ l.touched ? '' : '未涉及该批' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h2>调拨途中压货</h2>
      <div v-if="!data.in_transit.length" class="muted">无在途调拨。</div>
      <table v-else>
        <thead><tr><th>调拨单号</th><th>路径</th><th class="right">在途数量</th><th>发货时间</th></tr></thead>
        <tbody>
          <tr v-for="t in data.in_transit" :key="t.transfer_no">
            <td>{{ t.transfer_no }}</td><td>{{ t.from }} → {{ t.to }}</td>
            <td class="right"><b>{{ t.qty }}</b></td><td>{{ t.shipped_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h2>批次全流水（纸面对账用）</h2>
      <ul class="timeline">
        <li v-for="(e, i) in data.timeline" :key="i">
          <span class="muted">{{ e.time }}</span>
          <span class="badge" :style="{ margin: '0 8px' }"
                :class="e.qty < 0 ? 'near' : e.type.includes('质检') ? 'hold' : 'normal'">{{ e.type }}</span>
          {{ e.doc_no }}｜{{ e.location }}｜
          <b :style="{ color: e.qty < 0 ? 'var(--danger)' : 'var(--ok)' }">
            {{ e.qty > 0 ? '+' : '' }}{{ e.qty }}</b>
          <span class="muted" v-if="e.party">｜{{ e.party }}</span>
        </li>
      </ul>
    </div>

    <div class="panel">
      <h2>登记厂家召回函</h2>
      <div class="grid c4">
        <label class="fld">召回函号 <b>*</b><input v-model="notice.no" placeholder="如：ZH-2026-0918" /></label>
        <label class="fld">发函厂家/供应商 <b>*</b><input v-model="notice.issuer" /></label>
        <label class="fld">发函日期 <b>*</b><input type="date" v-model="notice.issued_date" /></label>
        <label class="fld">备注<input v-model="notice.note" /></label>
      </div>
      <div style="margin-top:12px">
        <button class="btn" :disabled="regBusy" @click="register">登记召回函</button>
      </div>
    </div>
  </template>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { toast } from '../toast'

const drugs = ref([])
const batchNo = ref('HG20260418')
const drugId = ref(null)
const data = ref(null)
const busy = ref(false)
const regBusy = ref(false)
const notice = ref({ no: '', issuer: '', issued_date: new Date().toISOString().slice(0, 10), note: '' })

async function trace() {
  if (!batchNo.value.trim()) return toast.err('请输入批号')
  busy.value = true
  try {
    const p = new URLSearchParams({ batch_no: batchNo.value.trim() })
    if (drugId.value) p.set('drug_id', drugId.value)
    data.value = await api.get(`/api/recalls/trace?${p}`)
  } catch (e) { data.value = null; toast.err(e) } finally { busy.value = false }
}

async function register() {
  if (!data.value) return toast.err('请先追溯出批次')
  const n = notice.value
  if (!n.no.trim() || !n.issuer.trim() || !n.issued_date) return toast.err('召回函号、发函方、发函日期必填')
  regBusy.value = true
  try {
    const r = await api.post('/api/recalls', {
      batch_id: data.value.batch.id, no: n.no.trim(), issuer: n.issuer.trim(),
      issued_date: n.issued_date, note: n.note || null,
    })
    toast.ok(`召回函 ${r.no} 已登记`)
    notice.value = { ...notice.value, no: '', issuer: '', note: '' }
  } catch (e) { toast.err(e) } finally { regBusy.value = false }
}

onMounted(async () => { drugs.value = await api.get('/api/drugs') })
</script>
