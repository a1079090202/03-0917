<template>
  <div class="panel">
    <h2>流水台账</h2>
    <div class="toolbar">
      <button v-for="t in tabs" :key="t.key" class="btn sm"
              :class="tab === t.key ? '' : 'gray'"
              @click="switchTab(t.key)">{{ t.label }}</button>
      <span class="spacer"></span>
      <button class="btn sm gray" @click="load">刷新</button>
    </div>

    <!-- 拆零台账（独立账本）-->
    <div v-if="tab === 'split'" class="tbl-wrap">
      <table>
        <thead><tr>
          <th>时间</th><th>关联出库单</th><th>门店</th><th>药品</th><th>批号</th>
          <th class="right">拆零售出</th><th>折合整包装</th><th>散卖零头</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.outbound_no + r.time + r.batch_no">
            <td>{{ r.time }}</td><td>{{ r.outbound_no }}</td><td>{{ r.location }}</td>
            <td>{{ r.drug_name }}</td><td><b>{{ r.batch_no }}</b></td>
            <td class="right"><b>{{ r.qty }}</b> {{ r.unit }}</td>
            <td class="right">{{ r.bulk_packages }} {{ r.bulk_unit }}</td>
            <td class="right">{{ r.loose_units }} {{ r.unit }}</td>
          </tr>
          <tr v-if="!rows.length"><td colspan="8" class="center muted">无拆零记录</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 入库 -->
    <div v-else-if="tab === 'inbound'" class="tbl-wrap">
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

    <!-- 出库 -->
    <div v-else-if="tab === 'outbound'" class="tbl-wrap">
      <table>
        <thead><tr>
          <th>出库单号</th><th>时间</th><th>货位</th><th>药品</th><th>类型</th>
          <th class="right">总数</th><th>批次明细</th><th>经办</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.no">
            <td>{{ r.no }}</td><td>{{ r.time }}</td><td>{{ r.location }}</td>
            <td>{{ r.drug_name }}</td>
            <td>{{ r.kind === 'split' ? '拆零' : '整包装' }}</td>
            <td class="right">{{ r.qty }} {{ r.unit }}</td>
            <td class="wrap">
              <details class="sub-flow" v-for="f in r.flows" :key="f.batch_id">
                <summary>{{ f.batch_no }}（至 {{ f.expiry_date }}）</summary>
                出 {{ f.qty }}
              </details>
            </td>
            <td>{{ r.operator }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 调拨 -->
    <div v-else-if="tab === 'transfer'" class="tbl-wrap">
      <table>
        <thead><tr>
          <th>调拨单号</th><th>发货时间</th><th>药品</th><th>调出→调入</th>
          <th class="right">数量</th><th>批次明细</th><th>状态</th><th>收货时间</th>
        </tr></thead>
        <tbody>
          <tr v-for="t in rows" :key="t.no">
            <td>{{ t.no }}</td><td>{{ t.shipped_at }}</td><td>{{ t.drug_name }}</td>
            <td>{{ t.from }} → {{ t.to }}</td><td class="right">{{ t.qty }} {{ t.unit }}</td>
            <td class="wrap">
              <span v-for="i in t.items" :key="i.batch_no" style="margin-right:10px">
                {{ i.batch_no }}:{{ i.qty }}
              </span>
            </td>
            <td><span class="badge" :class="t.status === 'in_transit' ? 'transit' : 'done'">
              {{ t.status === 'in_transit' ? '在途' : '已收货' }}</span></td>
            <td>{{ t.received_at || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 质检 -->
    <div v-else-if="tab === 'quality'" class="tbl-wrap">
      <table>
        <thead><tr>
          <th>单号</th><th>时间</th><th>药品</th><th>批号</th>
          <th>动作</th><th>放行单号</th><th>原因</th><th>经办</th>
        </tr></thead>
        <tbody>
          <tr v-for="q in rows" :key="q.no">
            <td>{{ q.no }}</td><td>{{ q.time }}</td><td>{{ q.drug_name }}</td>
            <td><b>{{ q.batch_no }}</b></td>
            <td><span class="badge" :class="q.action === 'hold' ? 'hold' : 'normal'">
              {{ q.action === 'hold' ? '停售' : '放行' }}</span></td>
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

const tabs = [
  { key: 'inbound', label: '入库流水', path: '/api/ledger/inbound' },
  { key: 'outbound', label: '出库流水', path: '/api/ledger/outbound' },
  { key: 'split', label: '拆零台账（独立）', path: '/api/ledger/splits' },
  { key: 'transfer', label: '调拨流水', path: '/api/ledger/transfers' },
  { key: 'quality', label: '质检台账', path: '/api/ledger/quality' },
]
const tab = ref('split')
const rows = ref([])

async function load() {
  const t = tabs.find((x) => x.key === tab.value)
  rows.value = await api.get(`${t.path}?limit=300`)
}
function switchTab(k) { tab.value = k; load() }

onMounted(load)
</script>
