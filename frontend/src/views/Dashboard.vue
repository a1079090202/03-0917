<template>
  <div>
    <h1>总览</h1>
    <div class="page-sub">库存、效期预警、在途调拨一屏掌握</div>

    <div class="stats" v-if="d">
      <div class="stat"><div class="num">{{ d.drug_count }}</div><div class="label">药品品种</div></div>
      <div class="stat"><div class="num">{{ d.batch_count }}</div><div class="label">批次数</div></div>
      <div class="stat good"><div class="num">{{ d.total_units }}</div><div class="label">库存总量（最小单位）</div></div>
      <div class="stat alert"><div class="num">{{ d.near_expiry_count }}</div><div class="label">近效期批次（6个月内）</div></div>
      <div class="stat danger"><div class="num">{{ d.expired_locked_count }}</div><div class="label">已过期锁死批次</div></div>
      <div class="stat danger"><div class="num">{{ d.qc_suspended_count }}</div><div class="label">质检停售批次</div></div>
      <div class="stat alert"><div class="num">{{ d.in_transit_count }}</div><div class="label">在途调拨单</div></div>
      <div class="stat"><div class="num">{{ d.store_count }}</div><div class="label">门店数</div></div>
    </div>

    <div class="card">
      <h2>近效期预警（效期前 6 个月）</h2>
      <table v-if="d && d.near_expiry.length">
        <thead><tr><th>药品</th><th>规格</th><th>批号</th><th>有效期至</th><th class="num-cell">剩余天数</th><th class="num-cell">在手库存</th></tr></thead>
        <tbody>
          <tr v-for="r in d.near_expiry" :key="r.batch_id">
            <td>{{ r.drug_name }}</td><td>{{ r.spec }}</td><td>{{ r.batch_no }}</td>
            <td>{{ r.expiry_date }}</td>
            <td class="num-cell"><span class="badge b-warn">{{ r.days_to_expiry }} 天</span></td>
            <td class="num-cell">{{ r.on_hand }} {{ r.unit }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="muted">暂无近效期批次</div>
    </div>

    <div class="card">
      <h2>在途调拨</h2>
      <table v-if="d && d.in_transit_list.length">
        <thead><tr><th>调拨单号</th><th>药品</th><th>批号</th><th>调出</th><th>调入</th><th class="num-cell">数量</th><th>发货时间</th></tr></thead>
        <tbody>
          <tr v-for="t in d.in_transit_list" :key="t.transfer_no">
            <td>{{ t.transfer_no }}</td><td>{{ t.drug_name }}</td><td>{{ t.batch_no }}</td>
            <td>{{ t.from_store }}</td><td>{{ t.to_store }}</td>
            <td class="num-cell">{{ t.quantity }}</td><td>{{ t.shipped_at }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="muted">暂无在途调拨</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const d = ref(null)
onMounted(async () => { d.value = await api.get('/api/dashboard') })
</script>
