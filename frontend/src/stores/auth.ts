import { defineStore } from 'pinia'
import type { User } from '@/types'
import { apiPost, USE_MOCK } from '@/api/client'

const TOKEN_KEY = 'qap_token'
const USER_KEY = 'qap_user'

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
      const data = await apiPost<{ token: string; user: User }>('/api/auth/login', {
        username,
        password,
      })
      this._persist(data.token, data.user)
    },

    async register(username: string, email: string, password: string) {
      const data = await apiPost<{ token: string; user: User }>('/api/auth/register', {
        username,
        email,
        password,
      })
      this._persist(data.token, data.user)
    },

    async guest() {
      // mock 模式直接本地构造游客身份，不请求后端
      if (USE_MOCK) {
        this._persist('guest-mock-token', { id: 0, username: 'guest', email: '' })
        return
      }
      const data = await apiPost<{ token: string; user: User }>('/api/auth/guest', {})
      this._persist(data.token, data.user)
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
