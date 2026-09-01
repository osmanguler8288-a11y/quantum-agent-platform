import { defineStore } from 'pinia'
import type { Conversation } from '@/types'

let seq = 0
const genId = () => `conv-${Date.now()}-${seq++}`

// mock 历史会话（联调时替换为 GET /api/conversations）
const MOCK_CONVERSATIONS: Conversation[] = [
  { id: 'conv-1', title: '优化苯的结构 B3LYP/6-31G*', updatedAt: '2026-08-16T09:00:00' },
  { id: 'conv-2', title: '计算甲醛的 TD-DFT 吸收光谱', updatedAt: '2026-08-15T14:20:00' },
  { id: 'conv-3', title: 'Ni 催化剂的频率分析', updatedAt: '2026-08-14T16:45:00' },
]

export const useConversationStore = defineStore('conversation', {
  state: () => ({
    conversations: MOCK_CONVERSATIONS as Conversation[],
    activeId: null as string | null,
  }),

  getters: {
    active: (state) => state.conversations.find((c) => c.id === state.activeId) ?? null,
  },

  actions: {
    newConversation() {
      this.activeId = null
    },

    switchTo(id: string) {
      this.activeId = id
    },
  },
})
