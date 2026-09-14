import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'

// 开发期代理：/api 转发到后端 FastAPI。
// 后端启动（backend 目录下）：uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
// 联调时把 VITE_USE_MOCK 设为 false 即可切到真实接口
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // 3dmol 的 main 指向 UMD 产物（module.exports = window.$3Dmol），
      // Vite 预打包无法正确解析默认导出，改为指向 ESM 产物（具名导出）。
      '3dmol': fileURLToPath(new URL('./node_modules/3dmol/build/3Dmol.es6.js', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // ⚠️ 必须与后端实际端口一致（README 写的是 8001，此前这里错写成 8000）
        // ⚠️ 必须写 127.0.0.1 而不是 localhost：
        //    Node 17+ 的 DNS 解析默认 prefer-IPv6，localhost 会先解析成 ::1，
        //    而 uvicorn 默认只绑 IPv4 → 代理请求连接失败（表现为前端拿到空响应）。
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
