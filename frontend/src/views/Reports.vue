<template>
  <div>
    <h1>月度报表</h1>
    <div class="page-sub">每月 1 号看上月：近效期清单 + 批次流向表，全部从库存流水汇总，可与台账逐笔对账</div>

    <div class="card no-print">
      <div class="toolbar">
        <label class="field">报表月份
          <input type="month" v-model="month" @change="load" />
        </label>
        <button class="primary" @click="load">刷新</button>
        <button @click="printAll">打印</button>
      </div>
    </div>

    <div class="card">
      <h2>{{ month }} 近效期清单（效期 ≤ {{ near.threshold }}，即月末+{{ near.window_months }}个月内到期）</h2>
      <table v-if="near.items && near.items.length">
        <thead><tr><th>药品</th><th>规格</th><th>批号</th><th>有效期至</th><th class="num-cell">月末结存</th><th class="num-cell">剩余天数</th><th>当前状态</th></tr></thead>
        <tbody>
          <tr v-for="i in near.items" :key="i.batch_id">
            <td>{{ i.drug_name }}</td><td>{{ i.spec }}</td><td>{{ i.batch_no }}</td>
            <td>{{ i.expiry_date }}</td>
            <td class="num-cell">{{ i.quantity_at_month_end }} {{ i.unit }}</td>
            <td class="num-cell">
              <span v-if="i.expired" class="badge b-bad">已过期</span>
              <span v-else class="badge b-warn">{{ i.days_to_expiry }} 天</span>
            </td>
            <td><span class="badge" :class="BATCH_STATUS[i.status].cls">{{ BATCH_STATUS[i.status].text }}</span></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="muted">该月无近效期批次在手</div>
    </div>

    <div class="card">
      <h2>{{ month }} 批次流向表（全连锁口径，单位：最小包装）</h2>
      <table>
        <thead>
          <tr><th>药品</th><th>批号</th><th>效期</th><th class="num-cell">期初</th><th class="num-cell">入库</th><th class="num-cell">销售</th><th class="num-cell">拆零</th><th class="num-cell">调入</th><th class="num-cell">调出</th><th class="num-cell">期末</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in flow.batches" :key="r.batch_id">
            <td>{{ r.drug_name }}</td><td>{{ r.batch_no }}</td><td>{{ r.expiry_date }}</td>
            <td class="num-cell">{{ r.opening }}</td>
            <td class="num-cell">{{ r.inbound }}</td>
            <td class="num-cell">{{ r.sale }}</td>
            <td class="num-cell">{{ r.split_sale }}</td>
            <td class="num-cell">{{ r.transfer_in }}</td>
            <td class="num-cell">{{ r.transfer_out }}</td>
            <td class="num-cell"><b>{{ r.closing }}</b></td>
          </tr>
          <tr v-if="flow.totals" style="font-weight:700;background:#f0f7f3">
            <td colspan="3">合计（{{ flow.batches.length }} 批次）</td>
            <td class="num-cell">{{ flow.totals.opening }}</td>
            <td class="num-cell">{{ flow.totals.inbound }}</td>
            <td class="num-cell">{{ flow.totals.sale }}</td>
            <td class="num-cell">{{ flow.totals.split_sale }}</td>
            <td class="num-cell">{{ flow.totals.transfer_in }}</td>
            <td class="num-cell">{{ flow.totals.transfer_out }}</td>
            <td class="num-cell"><b>{{ flow.totals.closing }}</b></td>
          </tr>
        </tbody>
      </table>
      <div class="muted mt">校验：期初 + 入库 + 调入 − 销售 − 拆零 − 调出 = 期末；与流水台账逐笔可对。</div>
    </div>

    <div class="card">
      <h2>{{ month }} 门店汇总</h2>
      <table>
        <thead><tr><th>门店</th><th class="num-cell">入库</th><th class="num-cell">销售</th><th class="num-cell">拆零</th><th class="num-cell">调入</th><th class="num-cell">调出</th></tr></thead>
        <tbody>
          <tr v-for="s in flow.stores" :key="s.store_id">
            <td>{{ s.store_name }}</td>
            <td class="num-cell">{{ s.inbound }}</td>
            <td class="num-cell">{{ s.sale }}</td>
            <td class="num-cell">{{ s.split_sale }}</td>
            <td class="num-cell">{{ s.transfer_in }}</td>
            <td class="num-cell">{{ s.transfer_out }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { BATCH_STATUS, lastMonth } from '../utils'

const month = ref(lastMonth())
const near = ref({ items: [] })
const flow = ref({ batches: [], stores: [], totals: null })

async function load() {
  const [n, f] = await Promise.all([
    api.get(`/api/reports/near-expiry?month=${month.value}`),
    api.get(`/api/reports/monthly-flow?month=${month.value}`),
  ])
  near.value = n
  flow.value = f
}

function printAll() { window.print() }

onMounted(load)
</script>
