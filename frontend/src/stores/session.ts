import { defineStore } from 'pinia'

const SESSION_KEY = 'qap_session_id'

/**
 * 「当前正在续接的会话」—— 存的就是后端的 `conversation.id`。
 *
 * ⚠️ 名字里的 session 是历史遗留：后端已经统一成**一个**标识符
 *    （conversation.id 即 workflow 的 session_id），所以这里不要再去区分两者。
 *
 * ⚠️ 它是**唯一被持久化**的会话状态（localStorage）。刷新页面后
 *    `conversation.activeId`（侧边栏高亮）会丢，靠这里恢复 —— 见
 *    stores/conversation.ts 的 load()。
 */
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
