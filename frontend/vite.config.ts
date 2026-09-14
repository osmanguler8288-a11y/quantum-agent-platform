import { defineConfig, loadEnv } from 'vite'
import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'

/**
 * 开发期代理：**所有 /api 一律走 Go 认证网关**。
 *
 *     浏览器 ──/api/*──→ 网关(:8080) ──校验 JWT 并注入 X-User-ID──→ FastAPI(:8001)
 *                            └─ /api/auth/* 由网关自己处理
 *
 * ⚠️ 为什么不能只把 /api/auth 分流给网关、其余直接给 FastAPI：
 *    FastAPI **自身不做任何鉴权**，它的用户身份完全来自网关注入的 X-User-ID 头。
 *    绕过网关直连 FastAPI 的话：
 *      - 未登录也能拿到数据（该 401 却返回 200）
 *      - 所有请求的身份都会退化成 default_user，记忆隔离/审计日志全部失真
 *
 * ⚠️ target 必须写 127.0.0.1 而不是 localhost：
 *    Node 17+ 的 DNS 默认 prefer-IPv6，localhost 先解析成 ::1，
 *    而网关绑 IPv4 → 代理请求连接失败（前端拿到空响应）。
 *
 * 本地一键启动网关 + FastAPI：backend/start-dev.ps1
 * 指向远程网关（本地不跑后端）：在 frontend/.env 里设
 *    VITE_GATEWAY_URL=http://<服务器>:8080
 * 改完本文件需要**重启 vite**（配置不参与热更新）。
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const gateway = env.VITE_GATEWAY_URL || 'http://127.0.0.1:8080'

  return {
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
          target: gateway,
          changeOrigin: true,
          // 网关没启动时，Vite 默认只回一个裸 500，前端显示「请求失败 (500)」，
          // 完全看不出原因。这里改成明确的 502 + 可读文案（遵循后端的
          // {error, code} 契约，前端 client.ts 会直接把这个 error 显示出来）。
          configure: (proxy) => {
            proxy.on('error', (err, _req, res) => {
              console.error(
                `\n[vite-proxy] ✖ 无法连接认证网关 ${gateway}\n` +
                `            原因: ${err.message}\n` +
                `            解决: 另开终端执行  cd backend; .\\start-dev.ps1\n`,
              )
              // res 在错误路径上可能是普通 socket，能力检测后再写
              if (res && !res.headersSent && typeof res.writeHead === 'function') {
                res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
                res.end(JSON.stringify({
                  error: `认证网关不可达（${gateway}）。请先启动后端：backend/start-dev.ps1`,
                  code: 'GATEWAY_UNREACHABLE',
                }))
              }
            })
          },
        },
      },
    },
  }
})
