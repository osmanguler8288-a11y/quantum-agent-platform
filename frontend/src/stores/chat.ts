import { defineStore } from 'pinia'
import type { ChatMessage, MessageBlock, PlanStep, SSEEvent, ToolResult } from '@/types'
import { USE_MOCK } from '@/api/client'
import { fetchConversationMessages } from '@/api/conversation'
import { streamWorkflow } from '@/api/sse'
import { mockEventStream } from '@/api/mock'
import { useConversationStore } from '@/stores/conversation'
import { useSessionStore } from '@/stores/session'

let seq = 0
const genId = () => `${Date.now()}-${seq++}`

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [] as ChatMessage[],
    isRunning: false,
  }),

  actions: {
    addUserMessage(text: string) {
      this.messages.push({ id: genId(), role: 'user', blocks: [{ type: 'text', text }] })
    },

    clear() {
      this.messages = []
    },

    /** 开始一段全新对话：清空消息 + 解除绑定，下一句会另起一条会话 */
    startNew() {
      this.messages = []
      useSessionStore().clear()
      useConversationStore().newConversation()
    },

    /**
     * 确保有一段可续接的会话，返回它的 id（失败返回 null）。
     *
     * ⚠️ 会话必须**先建后发**：id 由后端生成（全局主键单一来源），
     *    前端自己 rand 一个串既会碰撞、也无法与数据库对齐。
     *
     * ⚠️ 建会话失败**不阻断提问**：后端 /workflow/stream 里还有一次
     *    get_or_create 兜底，它会把真正使用的 id 通过 conversation_ready / done 回传。
     */
    async ensureConversation(title: string): Promise<string | null> {
      const session = useSessionStore()
      if (session.sessionId) return session.sessionId
      try {
        const id = await useConversationStore().create({
          model: 'default',
          title: title.trim().slice(0, 40),
        })
        session.setSession(id)
        return id
      } catch (e) {
        console.warn('[chat] 预建会话失败，交给后端兜底:', e)
        return null
      }
    },

    /**
     * 切换历史会话：拉取**真实的**消息并回填。
     *
     * 以前这里是 mock —— 只塞两条占位文本，点了历史对话看不到任何真实内容。
     * 现在走 GET /api/conversations/{id}/messages。
     */
    async loadConversation(id: string) {
      const session = useSessionStore()
      session.setSession(id)
      useConversationStore().switchTo(id)
      this.messages = []

      if (USE_MOCK) {
        this.messages.push({ id: genId(), role: 'user', blocks: [{ type: 'text', text: '（mock）历史对话' }] })
        this.messages.push({
          id: genId(),
          role: 'assistant',
          blocks: [{ type: 'thinking', text: '（mock）该会话历史记录将在联调后从后端加载' }],
        })
        return
      }

      try {
        const page = await fetchConversationMessages(id)
        this.messages = page.items
          // ⚠️ 过滤空 content：落库时已跳过空的 assistant 回复，
          //    这里再兜一次，避免历史里出现空气泡
          .filter((m) => (m.content || '').trim())
          .map((m) => ({
            id: genId(),
            role: m.role,
            blocks: [{ type: 'text', text: m.content }] as MessageBlock[],
          }))
      } catch (e) {
        this.messages = [{
          id: genId(),
          role: 'assistant',
          blocks: [{ type: 'error', message: `历史消息加载失败：${(e as Error).message}` }],
        }]
      }
    },

    async submit(query: string, structure?: unknown) {
      if (!query.trim() || this.isRunning) return

      this.addUserMessage(query)
      this.messages.push({ id: genId(), role: 'assistant', blocks: [] })
      this.isRunning = true

      // ⚠️ 必须操作 push 之后由响应式系统包装的那个**代理对象**，不能持有 push 前
      //    创建的原始对象去改 —— Vue 的 reactive 只在**通过代理访问**时才建立依赖，
      //    直接改原始对象的嵌套属性不会触发任何重渲染。
      //    踩这个坑的表现是：SSE 事件全部正常收到、数据也对，但界面在流式过程中
      //    一个字都不更新，直到最后 isRunning 变化才一次性把攒的文本全渲染出来。
      const assistant = this.messages[this.messages.length - 1]

      const session = useSessionStore()

      const onEvent = (ev: SSEEvent) => this._applyEvent(assistant, ev, session, query)

      try {
        if (USE_MOCK) {
          for await (const ev of mockEventStream(query)) {
            onEvent(ev)
          }
        } else {
          // 先拿会话 id 再发消息 —— 这样第一轮就是带归属的，
          // 而不是等后端兜底建一条再回头补 id
          const conversationId = await this.ensureConversation(query)
          await streamWorkflow(
            { input_data: { user_query: query, ...(structure ? { structure } : {}) }, session_id: conversationId },
            onEvent,
          )
        }
      } catch (e) {
        assistant.blocks.push({ type: 'error', message: (e as Error).message })
      } finally {
        this.isRunning = false
      }
    },

    _applyEvent(
      msg: ChatMessage,
      ev: SSEEvent,
      session: ReturnType<typeof useSessionStore>,
      query = '',
    ) {
      switch (ev.event) {
        case 'thinking_chunk': {
          const last = msg.blocks[msg.blocks.length - 1]
          if (last && last.type === 'thinking') {
            last.text += ev.data
          } else {
            msg.blocks.push({ type: 'thinking', text: ev.data })
          }
          break
        }
        case 'plan_done': {
          msg.blocks.push({ type: 'plan', plan: ev.data })
          break
        }
        case 'step_start': {
          this._upsertStep(msg, ev.data.index, ev.data.step, 'running')
          break
        }
        case 'step_done': {
          this._upsertStep(msg, ev.data.index, undefined, ev.data.result.status === 'success' ? 'done' : 'fail', ev.data.result)
          break
        }
        case 'verdict_done': {
          msg.blocks.push({ type: 'verdict', verdict: ev.data })
          break
        }
        case 'retry': {
          msg.blocks.push({ type: 'retry', retryCount: ev.data.retry_count })
          break
        }
        case 'result_viz': {
          msg.blocks.push({ type: 'viz', viz: ev.data })
          break
        }
        case 'conversation_ready': {
          // 后端确认了会话。id 可能与请求里带的不同（我们传了不存在或别人的 id 时
          // 后端会换一个新的），所以以这里收到的为准。
          const id = ev.data.conversation_id
          session.setSession(id)
          const conversation = useConversationStore()
          conversation.switchTo(id)
          // 只有预建失败时才需要补一条本地占位 —— 否则 upsert 会把
          // POST /api/conversations 带回来的真实标题覆盖成空的
          if (!conversation.conversations.some((c) => c.id === id)) {
            conversation.upsert({
              id,
              title: query.trim().slice(0, 40),
              updated_at: new Date().toISOString(),
            })
          }
          break
        }
        case 'done': {
          msg.blocks.push({ type: 'done', status: ev.data.status })
          const id = ev.data.conversation_id || ev.data.session_id
          if (id) session.setSession(id)
          break
        }
        case 'error': {
          msg.blocks.push({ type: 'error', message: ev.data.message })
          break
        }
        default:
          break
      }
    },

    _upsertStep(
      msg: ChatMessage,
      index: number,
      step?: PlanStep,
      status?: 'running' | 'done' | 'fail',
      result?: ToolResult,
    ) {
      let stepsBlock = msg.blocks.find((b): b is Extract<MessageBlock, { type: 'steps' }> => b.type === 'steps')
      if (!stepsBlock) {
        stepsBlock = { type: 'steps', steps: [] }
        msg.blocks.push(stepsBlock)
      }
      const existing = stepsBlock.steps.find((s) => s.index === index)
      if (existing) {
        if (status) existing.status = status
        if (result) existing.result = result
      } else {
        stepsBlock.steps.push({ index, step, status: status ?? 'running', result })
      }
    },
  },
})
