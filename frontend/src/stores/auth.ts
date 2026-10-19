import { defineStore } from 'pinia'
import type { User } from '@/types'
import { apiPost } from '@/api/client'

const TOKEN_KEY = 'qap_token'
const USER_KEY = 'qap_user'

/**
 * 认证说明（改之前先读）
 *
 * 认证接口不在 FastAPI 上，而在 **Go 网关**（:9000）。链路由 vite 代理分流：
 *
 *     /api/auth/*  → Go 网关 :9000   ← 本文件调的接口
 *     /api/*       → FastAPI :8001
 *
 * 所以本文件正常工作有两个前提：
 *   1. Go 网关在跑（backend/start-dev.ps1 会一起启动）
 *   2. [vite.config.ts] 里的 '/api/auth' 分流规则在 '/api' 之前 —— 少了它就会 404
 *
 * 网关校验 JWT 后向下游注入 X-User-ID/[X-Username]，FastAPI 侧不再做任何鉴权。
 */
const AUTH_BACKEND_READY = true

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: JSON.parse(localStorage.getItem(USER_KEY) || 'null') as User | null,
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
  },

  actions: {
    async login(username: string, password: string) {
      if (!AUTH_BACKEND_READY) {
        throw new Error('账号登录需要 Go 网关（尚未部署）。请使用下方「直接进入（游客模式）」。')
      }
      const data = await apiPost<{ token: string; user: User }>('/api/auth/login', {
        username,
        password,
      })
      this._persist(data.token, data.user)
    },

    async register(username: string, email: string, password: string) {
      if (!AUTH_BACKEND_READY) {
        throw new Error('账号注册需要 Go 网关（尚未部署）。请使用下方「直接进入（游客模式）」。')
      }
      const data = await apiPost<{ token: string; user: User }>('/api/auth/register', {
        username,
        email,
        password,
      })
      this._persist(data.token, data.user)
    },

    async guest() {
      // 优先走网关拿真实 JWT（这样 token 能通过后续接口的校验）；
      // 网关没起时退回本地构造，保证前端单独跑也能进得去。
      try {
        const data = await apiPost<{ token: string; user: User }>('/api/auth/guest', {})
        this._persist(data.token, data.user)
      } catch {
        console.warn('[auth] 网关不可用，游客模式退回本地身份（受保护接口会 401）')
        this._persist('guest-local-token', { id: 0, username: 'guest', email: '' })
      }
    },

    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },

    _persist(token: string, user: User) {
      this.token = token
      this.user = user
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
  },
})
