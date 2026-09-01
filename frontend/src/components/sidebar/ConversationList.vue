<template>
  <div class="conv-section">
    <button class="new-btn" :title="collapsed ? '新建对话' : undefined" @click="onNew">
      <span class="icon">＋</span>
      <span v-if="!collapsed" class="label">新建对话</span>
    </button>

    <div v-if="!collapsed" class="list">
      <div
        v-for="c in sorted"
        :key="c.id"
        class="conv-item"
        :class="{ active: c.id === conv.activeId }"
        @click="onSwitch(c)"
      >
        <div class="conv-row">
          <span class="title">{{ c.title }}</span>
          <span class="time">{{ formatTime(c.updatedAt) }}</span>
        </div>
      </div>

      <div v-if="sorted.length === 0" class="empty">暂无历史对话</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Conversation } from '@/types'
import { useConversationStore } from '@/stores/conversation'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'

defineProps<{ collapsed: boolean }>()

const conv = useConversationStore()
const chat = useChatStore()
const session = useSessionStore()

const sorted = computed(() =>
  [...conv.conversations].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
)

function onNew() {
  conv.newConversation()
  chat.clear()
  session.clear()
}

function onSwitch(c: Conversation) {
  conv.switchTo(c.id)
  session.setSession(c.id)
  chat.loadConversation(c.id, c.title)
}

function formatTime(ts: string): string {
  return ts.replace('T', ' ').slice(0, 16)
}
</script>

<style scoped>
.conv-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.new-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  color: var(--orange);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.new-btn:hover {
  border-color: var(--orange);
  background: var(--orange-light);
}
.new-btn .icon {
  font-size: 16px;
  line-height: 1;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.conv-item {
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s;
}
.conv-item:hover {
  background: #f5f5f4;
}
.conv-item.active {
  background: var(--orange-light);
}

.conv-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.title {
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-item.active .title {
  color: var(--orange-hover);
  font-weight: 600;
}

.time {
  font-size: 11px;
  color: var(--text-secondary);
}

.empty {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
  padding: 12px 0;
}
</style>
