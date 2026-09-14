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

      <div v-if="!sorted.length" class="empty">
        {{ conv.loading && !conv.loaded ? '加载中…' : '暂无历史对话' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { Conversation } from '@/types'
import { useConversationStore } from '@/stores/conversation'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'

defineProps<{ collapsed: boolean }>()

const route = useRoute()
const router = useRouter()
const conv = useConversationStore()
const chat = useChatStore()
const session = useSessionStore()

const sorted = computed(() =>
  [...conv.conversations].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
)

// 历史对话来自真实接口（后端未就绪时保持空列表）
onMounted(() => conv.load())

/** 新建对话：清空当前会话并直接进入新对话界面（不再依赖调用方所在页面） */
function onNew() {
  conv.newConversation()
  chat.clear()
  session.clear()
  if (route.name !== 'chat') router.push({ name: 'chat' })
}

function onSwitch(c: Conversation) {
  conv.switchTo(c.id)
  session.setSession(c.id)
  chat.loadConversation(c.id, c.title)
}

/** 侧边栏用紧凑的本地时间（后端下发的是 ISO/UTC，直接切片会差 8 小时） */
function formatTime(ts: string): string {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
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
