import { defineStore } from 'pinia'
import type { Conversation } from '@/types'
import { fetchConversations } from '@/api/conversation'
import { isApiNotFound } from '@/api/client'

/** 侧边栏「历史对话」一次展示的条数（分页只在对话管理页做） */
const SIDEBAR_LIMIT = 20

/**
 * 会话 store —— 只负责侧边栏那一小段「历史对话」+ 当前选中的会话。
 * 数据来自真实接口 GET /api/conversations；后端未就绪（404）时保持空列表。
 */
export const useConversationStore = defineStore('conversation', {
  state: () => ({
    /** 侧边栏历史对话（真实接口下发；后端未就绪时为 []） */
    conversations: [] as Conversation[],
    activeId: null as string | null,
    loading: false,
    /** 是否已成功拿到过一次列表（用于区分「加载中」与「确实没有」） */
    loaded: false,
  }),

  getters: {
    active: (state) => state.conversations.find((c) => c.id === state.activeId) ?? null,
  },

  actions: {
    /**
     * 拉取侧边栏历史对话。
     * - 404（后端暂无 /api/conversations 路由）→ 空列表，不报错
     * - 其他错误（500 / 断网）→ 保留原列表，静默失败（侧边栏不适合弹错误）
     */
    async load() {
      this.loading = true
      try {
        const resp = await fetchConversations({ tab: 'all', page: 1, page_size: SIDEBAR_LIMIT })
        this.conversations = resp.items
          .filter((x) => !x.archived) // 已归档的只在对话管理页查看
          .map((x) => ({ id: String(x.id), title: x.title, updatedAt: x.updated_at }))
        this.loaded = true
      } catch (e) {
        if (isApiNotFound(e)) {
          this.conversations = []
          this.loaded = true
        }
      } finally {
        this.loading = false
      }
    },

    /** 新建对话：解绑当前会话（新对话界面 = 没有 activeId） */
    newConversation() {
      this.activeId = null
    },

    switchTo(id: string) {
      this.activeId = id
    },

    /** 本地登记/更新一条会话（新建、继续对话、改名后同步侧边栏，避免整表重拉） */
    upsert(c: { id: number | string; title: string; updated_at: string }): string {
      const sid = String(c.id)
      const existing = this.conversations.find((x) => x.id === sid)
      if (existing) {
        existing.title = c.title
        existing.updatedAt = c.updated_at
      } else {
        this.conversations.unshift({ id: sid, title: c.title, updatedAt: c.updated_at })
      }
      return sid
    },

    /** 本地移除（删除成功后同步侧边栏） */
    remove(id: number | string) {
      const sid = String(id)
      const i = this.conversations.findIndex((x) => x.id === sid)
      if (i >= 0) this.conversations.splice(i, 1)
      if (this.activeId === sid) this.activeId = null
    },
  },
})
