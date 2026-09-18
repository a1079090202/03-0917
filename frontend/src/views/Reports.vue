<template>
  <div class="panel">
    <h2>月度报表（默认上月，每月 1 号出账）</h2>
    <div class="toolbar">
      <label class="fld">年份<input type="number" v-model.number="year" style="width:110px" /></label>
      <label class="fld">月份
        <select v-model.number="month">
          <option v-for="m in 12" :key="m" :value="m">{{ m }} 月</option>
        </select>
      </label>
      <button class="btn" @click="load">出账</button>
      <span class="spacer"></span>
      <span class="muted">月末快照口径：近效期清单按月末日期 + 6 个月窗口，只列月末仍有库存的批</span>
    </div>

    <template v-if="data">
      <p class="muted">
        账期：{{ data.period.start }} ~ {{ data.period.end }}（不含当日）
      </p>

      <div class="grid c3" style="margin-bottom:14px">
        <div class="stat warn"><div class="n">{{ data.near_expiry.length }}</div><div class="l">上月末近效期批次（6个月内）</div></div>
        <div class="stat danger"><div class="n">{{ data.expired.length }}</div><div class="l">上月末已过期未清批次</div></div>
        <div class="stat" style="--primary-dark:#7b3f8f"><div class="n" style="color:#7b3f8f">{{ data.quality_hold.length }}</div><div class="l">上月末质检停售批次</div></div>
      </div>

      <h3>① 近效期清单（效期前 6 个月）</h3>
      <div class="tbl-wrap" style="max-height:34vh">
        <table>
          <thead><tr>
            <th>药品</th><th>批号</th><th>有效期至</th><th>供应商</th>
            <th class="right">月末在架</th><th class="right">其中在途</th><th>状态</th>
          </tr></thead>
          <tbody>
            <tr v-for="r in data.near_expiry" :key="r.batch_id" style="background:#fffcf5">
              <td>{{ r.drug_code }} {{ r.drug_name }}</td><td><b>{{ r.batch_no }}</b></td>
              <td>{{ r.expiry_date }}</td><td>{{ r.supplier }}</td>
              <td class="right">{{ r.on_shelf_qty }}</td>
              <td class="right">{{ r.in_transit_qty }}</td>
              <td><span class="badge" :class="r.quality_status === 'hold' ? 'hold' : 'near'">
                {{ r.quality_status === 'hold' ? '同时停售' : '近效期' }}</span></td>
            </tr>
            <tr v-if="!data.near_expiry.length"><td colspan="7" class="center muted">无</td></tr>
          </tbody>
        </table>
      </div>

      <h3>② 已过期未清批次（须立即隔离销毁）</h3>
      <div class="tbl-wrap" style="max-height:24vh">
        <table>
          <thead><tr><th>药品</th><th>批号</th><th>有效期至</th><th class="right">月末存量</th></tr></thead>
          <tbody>
            <tr v-for="r in data.expired" :key="r.batch_id" style="background:#fff5f4">
              <td>{{ r.drug_name }}</td><td><b>{{ r.batch_no }}</b></td>
              <td>{{ r.expiry_date }}</td><td class="right">{{ r.closing_qty }}</td>
            </tr>
            <tr v-if="!data.expired.length"><td colspan="4" class="center muted">无</td></tr>
          </tbody>
        </table>
      </div>

      <h3>③ 批次流向表（按效期排序）</h3>
      <div class="tbl-wrap">
        <table>
          <thead><tr>
            <th>药品</th><th>批号</th><th>有效期至</th>
            <th class="right">月初存量</th><th class="right">本月入库</th>
            <th class="right">本月销售(含拆零)</th><th class="right">本月调入</th>
            <th class="right">本月调出</th><th class="right">月末在途</th>
            <th class="right">月末在架</th><th class="right">月末合计</th><th>质量</th>
          </tr></thead>
          <tbody>
            <tr v-for="r in data.batch_flows" :key="r.batch_id">
              <td class="wrap">{{ r.drug_name }}</td><td><b>{{ r.batch_no }}</b></td>
              <td>{{ r.expiry_date }}</td>
              <td class="right">{{ r.opening_qty }}</td>
              <td class="right">{{ r.inbound_qty }}</td>
              <td class="right">{{ r.sold_qty }}</td>
              <td class="right">{{ r.received_qty }}</td>
              <td class="right">{{ r.shipped_qty }}</td>
              <td class="right">{{ r.in_transit_qty }}</td>
              <td class="right">{{ r.on_shelf_qty }}</td>
              <td class="right"><b>{{ r.closing_qty }}</b></td>
              <td><span v-if="r.quality_status === 'hold'" class="badge hold">停售</span>
                  <span v-else class="muted">—</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="muted" style="margin-top:8px">
        注：月末合计 = 月初存量 + 本月入库 − 本月销售（调拨只改货位，不改变全连锁总量，故单列核对）。
      </p>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const now = new Date()
const year = ref(now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear())
const month = ref(now.getMonth() === 0 ? 12 : now.getMonth())
const data = ref(null)

async function load() {
  data.value = await api.get(`/api/reports/monthly?year=${year.value}&month=${month.value}`)
}
onMounted(load)
</script>
