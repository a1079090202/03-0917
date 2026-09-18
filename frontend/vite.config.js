import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 构建产物直接输出到项目根 frontend_dist/，由 FastAPI 托管
export default defineConfig({
  plugins: [vue()],
  base: '/',
  build: {
    outDir: '../frontend_dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
