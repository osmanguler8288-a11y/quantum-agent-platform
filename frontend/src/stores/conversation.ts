import { defineStore } from 'pinia'
import type { Conversation } from '@/types'
import {
  createConversation,
  fetchConversations,
  type ConvCreatePayload,
} from '@/api/conversation'
import { isApiNotFound } from '@/api/client'
import { useSessionStore } from '@/stores/session'

/** 侧边栏「历史对话」一次展示的条数（分页只在对话管理页做） */
const SIDEBAR_LIMIT = 20

/**
 * 会话 store —— 负责侧边栏那段「历史对话」+ 当前选中的会话。
 * 数据来自真实接口 GET /api/conversations。
 *
 * ⚠️ id 一律是 **string**，与后端 conversation.id 一致。
 *    别再引入 `String(x.id)` 这类转换 —— 那正是「同一实体两个标识符」的起点，
 *    后端的 session_id / conversation_id 曾经就是这样漂移开的。
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
     * - 404（后端路由不存在）→ 空列表，不报错
     * - 其他错误（500 / 503 / 断网）→ 保留原列表，静默失败（侧边栏不适合弹错误）
     */
    async load() {
      this.loading = true
      try {
        const resp = await fetchConversations({ tab: 'all', page: 1, page_size: SIDEBAR_LIMIT })
        this.conversations = resp.items
          .filter((x) => !x.archived) // 已归档的只在对话管理页查看
          .map((x) => ({ id: x.id, title: x.title, updatedAt: x.updated_at }))
        this.loaded = true

        // ⚠️ 刷新页面后 activeId 会丢（它没进 localStorage），但 sessionId 还在。
        //    不同步的话会出现：聊天页接着旧会话继续发消息，侧边栏却一条都没高亮。
        const sid = useSessionStore().sessionId
        if (sid && this.conversations.some((c) => c.id === sid)) this.activeId = sid
      } catch (e) {
        if (isApiNotFound(e)) {
          this.conversations = []
          this.loaded = true
        }
      } finally {
        this.loading = false
      }
    },

    /**
     * 建一条真实会话并返回它的 id。
     *
     * ⚠️ id 由**后端**生成，前端不自己造 —— 全局主键必须单一来源，
     *    前端自己 rand 出来的 8 位串既会碰撞，也无法与数据库对齐。
     */
    async create(payload: ConvCreatePayload = { model: 'default' }): Promise<string> {
      const c = await createConversation(payload)
      const sid = this.upsert(c)
      this.activeId = sid
      return sid
    },

    /** 新建对话：解绑当前会话（新对话界面 = 没有 activeId） */
    newConversation() {
      this.activeId = null
    },

    switchTo(id: string) {
      this.activeId = id
    },

    /** 本地登记/更新一条会话（新建、继续对话、改名后同步侧边栏，避免整表重拉） */
    upsert(c: { id: string; title: string; updated_at: string }): string {
      const existing = this.conversations.find((x) => x.id === c.id)
      if (existing) {
        existing.title = c.title
        existing.updatedAt = c.updated_at
      } else {
        this.conversations.unshift({ id: c.id, title: c.title, updatedAt: c.updated_at })
      }
      return c.id
    },

    /** 本地移除（删除成功后同步侧边栏） */
    remove(id: string) {
      const i = this.conversations.findIndex((x) => x.id === id)
      if (i >= 0) this.conversations.splice(i, 1)
      if (this.activeId === id) this.activeId = null
    },
  },
})
