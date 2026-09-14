import { defineStore } from 'pinia'
import type { User } from '@/types'
import { apiPost } from '@/api/client'

const TOKEN_KEY = 'qap_token'
const USER_KEY = 'qap_user'

/**
 * ⚠️ 认证的特殊性（联调期间必读）
 *
 * 后端**目前没有 /api/auth/* 接口** —— 认证的设计是由 Go 网关校验 JWT 后
 * 向下游注入 `X-User-ID` header，FastAPI 侧不做登录。所以：
 *
 *   - 游客模式：**永远本地构造**，不请求后端。它不该受 VITE_USE_MOCK 影响，
 *     否则一关 mock 就登录不进去（表现为 404 /api/auth/guest）。
 *   - 账号登录 / 注册：需要真实的 Go 网关，当前环境调用会 404。
 *     这里给出明确提示，而不是抛一个看不懂的网络错误。
 *
 * 将来 Go 网关就位后，把 login/register 的实现接上即可，guest 可保留为本地体验入口。
 */
const AUTH_BACKEND_READY = false

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
      // 始终本地构造游客身份 —— 后端没有认证接口，见文件顶部说明
      this._persist('guest-local-token', { id: 0, username: 'guest', email: '' })
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
