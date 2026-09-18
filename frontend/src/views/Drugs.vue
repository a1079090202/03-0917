<template>
  <div>
    <h1>药品目录</h1>
    <div class="page-sub">连锁统一药品字典；数量一律按最小包装单位存整数</div>

    <div class="card">
      <h2>新增药品</h2>
      <div v-if="err" class="msg err">{{ err }}</div>
      <div v-if="ok" class="msg ok">{{ ok }}</div>
      <div class="form-grid">
        <label class="field">编码 <input v-model.trim="form.code" placeholder="如 D016" /></label>
        <label class="field">通用名 <input v-model.trim="form.name" placeholder="药品名称" /></label>
        <label class="field">规格 <input v-model.trim="form.spec" placeholder="如 0.25g×24粒/盒" /></label>
        <label class="field">最小包装单位 <input v-model.trim="form.unit" placeholder="盒/瓶/支" style="width:100px" /></label>
        <label class="field">生产企业 <input v-model.trim="form.manufacturer" /></label>
        <button class="primary" @click="submit">保存</button>
      </div>
    </div>

    <div class="card">
      <h2>在用药品（{{ rows.length }}）</h2>
      <table>
        <thead><tr><th>编码</th><th>通用名</th><th>规格</th><th>最小单位</th><th>生产企业</th></tr></thead>
        <tbody>
          <tr v-for="d in rows" :key="d.id">
            <td>{{ d.code }}</td><td>{{ d.name }}</td><td>{{ d.spec }}</td>
            <td>{{ d.unit }}</td><td>{{ d.manufacturer }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'

const rows = ref([])
const err = ref('')
const ok = ref('')
const form = reactive({ code: '', name: '', spec: '', unit: '', manufacturer: '' })

async function load() { rows.value = await api.get('/api/drugs') }

async function submit() {
  err.value = ''; ok.value = ''
  if (!form.code || !form.name || !form.spec || !form.unit) { err.value = '编码、名称、规格、最小单位必填'; return }
  try {
    await api.post('/api/drugs', form)
    ok.value = `药品 ${form.name} 已加入目录`
    form.code = form.name = form.spec = form.unit = form.manufacturer = ''
    await load()
  } catch (e) { err.value = e.message }
}

onMounted(load)
</script>
