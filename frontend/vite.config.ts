import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'

// 开发期代理：/api 转发到后端 FastAPI（:8000），认证走 Go 网关（:8080）
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
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
