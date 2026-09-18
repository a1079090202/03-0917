<template>
  <div>
    <h1>召回追溯</h1>
    <div class="page-sub">厂家召回函到了？输批号，一口气列出：发过哪些门店、各卖了多少、还剩多少、在途压在哪</div>

    <div class="card">
      <div class="toolbar">
        <input v-model.trim="batchNo" placeholder="输入批号，如 AMX2601A" style="width:220px"
               @keyup.enter="trace" />
        <select v-model.number="drugId">
          <option :value="0">全部药品（批号唯一时可不选）</option>
          <option v-for="d in drugs" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
        <button class="primary" @click="trace" :disabled="!batchNo">追溯</button>
      </div>
      <div v-if="err" class="msg err">{{ err }}</div>
    </div>

    <template v-if="r">
      <div class="card">
        <h2>{{ r.batch.drug_name }}（{{ r.batch.spec }}）· 批号 {{ r.batch.batch_no }}</h2>
        <div class="stats">
          <div class="stat"><div class="num">{{ r.total_inbound }}</div><div class="label">总入库（{{ r.batch.unit }}）</div></div>
          <div class="stat good"><div class="num">{{ r.total_on_hand }}</div><div class="label">全链在手库存</div></div>
          <div class="stat"><div class="num">{{ r.total_sold }}</div><div class="label">已售出</div></div>
          <div class="stat alert"><div class="num">{{ r.total_in_transit }}</div><div class="label">调拨在途</div></div>
        </div>
        <div>
          对账：{{ r.total_inbound }} = {{ r.total_on_hand }}（在库）+ {{ r.total_sold }}（已售）+ {{ r.total_in_transit }}（在途）
          <span :class="r.reconciled ? 'reconcile-ok' : 'reconcile-bad'">
            {{ r.reconciled ? '✓ 账实相符' : '✗ 账实不符，立即核查！' }}
          </span>
        </div>
        <div class="muted mt">
          生产 {{ r.batch.production_date }} ｜ 效期 {{ r.batch.expiry_date }} ｜ 供应商 {{ r.batch.supplier }} ｜
          状态 <span class="badge" :class="BATCH_STATUS[r.batch.status].cls">{{ BATCH_STATUS[r.batch.status].text }}</span>
        </div>
      </div>

      <div class="card">
        <h2>各点分布（{{ r.locations.length }} 个点）</h2>
        <table>
          <thead><tr><th>门店/仓库</th><th class="num-cell">在手库存</th><th class="num-cell">已售（含拆零）</th><th class="num-cell">调入</th><th class="num-cell">调出</th></tr></thead>
          <tbody>
            <tr v-for="loc in r.locations" :key="loc.store_id">
              <td>{{ loc.store_name }}<span v-if="loc.is_warehouse" class="badge b-muted">总仓</span></td>
              <td class="num-cell"><b>{{ loc.on_hand }}</b></td>
              <td class="num-cell">{{ loc.sold }}<span v-if="loc.split_sold" class="muted">（拆零 {{ loc.split_sold }}）</span></td>
              <td class="num-cell">{{ loc.transferred_in }}</td>
              <td class="num-cell">{{ loc.transferred_out }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h2>调拨在途</h2>
        <table v-if="r.in_transit.length">
          <thead><tr><th>调拨单号</th><th>调出</th><th>调入</th><th class="num-cell">数量</th><th>发货时间</th><th>经办人</th></tr></thead>
          <tbody>
            <tr v-for="t in r.in_transit" :key="t.transfer_no">
              <td>{{ t.transfer_no }}</td><td>{{ t.from_store }}</td><td>{{ t.to_store }}</td>
              <td class="num-cell"><b>{{ t.quantity }}</b></td><td>{{ t.shipped_at }}</td><td>{{ t.operator }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="muted">无在途</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { BATCH_STATUS } from '../utils'

const drugs = ref([])
const batchNo = ref('')
const drugId = ref(0)
const r = ref(null)
const err = ref('')

async function trace() {
  err.value = ''; r.value = null
  try {
    const params = new URLSearchParams({ batch_no: batchNo.value })
    if (drugId.value) params.set('drug_id', drugId.value)
    r.value = await api.get('/api/recall/trace?' + params.toString())
  } catch (e) {
    err.value = e.message
  }
}

onMounted(async () => { drugs.value = await api.get('/api/drugs') })
</script>
