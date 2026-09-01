import { defineStore } from 'pinia'

const SESSION_KEY = 'qap_session_id'

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessionId: localStorage.getItem(SESSION_KEY) || '',
  }),

  getters: {
    hasSession: (state) => !!state.sessionId,
  },

  actions: {
    setSession(id: string) {
      this.sessionId = id
      localStorage.setItem(SESSION_KEY, id)
    },
    clear() {
      this.sessionId = ''
      localStorage.removeItem(SESSION_KEY)
    },
  },
})
