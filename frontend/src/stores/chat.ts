import { defineStore } from 'pinia'
import type { ChatMessage, MessageBlock, PlanStep, SSEEvent, ToolResult } from '@/types'
import { USE_MOCK } from '@/api/client'
import { streamWorkflow } from '@/api/sse'
import { mockEventStream } from '@/api/mock'
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

    // 切换历史会话：mock 模式塞入占位历史，联调后改为拉取后端消息
    loadConversation(id: string, title?: string) {
      this.messages = []
      if (USE_MOCK) {
        this.messages.push({ id: genId(), role: 'user', blocks: [{ type: 'text', text: title || '历史对话' }] })
        this.messages.push({
          id: genId(),
          role: 'assistant',
          blocks: [{ type: 'thinking', text: '（mock）该会话历史记录将在联调后从后端加载' }],
        })
      }
    },

    async submit(query: string, structure?: unknown) {
      if (!query.trim() || this.isRunning) return

      this.addUserMessage(query)
      const assistant: ChatMessage = { id: genId(), role: 'assistant', blocks: [] }
      this.messages.push(assistant)
      this.isRunning = true

      const session = useSessionStore()

      const onEvent = (ev: SSEEvent) => this._applyEvent(assistant, ev, session)

      try {
        if (USE_MOCK) {
          for await (const ev of mockEventStream(query)) {
            onEvent(ev)
          }
        } else {
          await streamWorkflow(
            { input_data: { user_query: query, ...(structure ? { structure } : {}) }, session_id: session.sessionId || null },
            onEvent,
          )
        }
      } catch (e) {
        assistant.blocks.push({ type: 'error', message: (e as Error).message })
      } finally {
        this.isRunning = false
      }
    },

    _applyEvent(msg: ChatMessage, ev: SSEEvent, session: ReturnType<typeof useSessionStore>) {
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
        case 'done': {
          msg.blocks.push({ type: 'done', status: ev.data.status })
          if (ev.data.session_id) session.setSession(ev.data.session_id)
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
