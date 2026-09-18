import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    // 构建产物直接交给 FastAPI 静态托管，总仓老电脑无需装 Node
    outDir: '../backend/app/static',
    emptyOutDir: true,
  },
})
