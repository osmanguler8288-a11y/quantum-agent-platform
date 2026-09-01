<template>
  <header class="header">
    <h1 class="title">{{ title }}</h1>
    <span v-if="chat.isRunning" class="running">
      <span class="dot"></span>运行中
    </span>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useConversationStore } from '@/stores/conversation'
import { useChatStore } from '@/stores/chat'

const conversation = useConversationStore()
const chat = useChatStore()

const title = computed(() => conversation.active?.title || '新对话')
</script>

<style scoped>
.header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 14px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.title {
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.running {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--orange);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--orange);
  animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.3;
  }
}
</style>
