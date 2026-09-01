<template>
  <div class="chat-view">
    <Sidebar @show-memory="showMemory = true" @logout="onLogout" />

    <div class="main">
      <Header />

      <div ref="chatEl" class="chat">
        <div v-if="chat.messages.length === 0" class="empty">
          <div class="icon">⚛</div>
          <div class="title">LLM-driven Computational Chemistry Agent</div>
          <div class="sub">输入科研任务，AI 自动拆解、执行工具、检查结果并自动纠错</div>
        </div>

        <Message
          v-for="m in chat.messages"
          :key="m.id"
          :message="m"
          :is-running="chat.isRunning && m.id === lastMessageId"
        />
      </div>

      <InputBar :is-running="chat.isRunning" @submit="onSubmit" />
    </div>

    <MemoryPanel :visible="showMemory" @close="showMemory = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useSessionStore } from '@/stores/session'
import { useConversationStore } from '@/stores/conversation'
import Sidebar from '@/components/Sidebar.vue'
import Header from '@/components/Header.vue'
import Message from '@/components/Message.vue'
import InputBar from '@/components/InputBar.vue'
import MemoryPanel from '@/components/MemoryPanel.vue'

const router = useRouter()
const chat = useChatStore()
const auth = useAuthStore()
const session = useSessionStore()
const conversation = useConversationStore()

const chatEl = ref<HTMLElement>()
const showMemory = ref(false)

const lastMessageId = computed(() => chat.messages[chat.messages.length - 1]?.id)

async function onSubmit(query: string, structure?: { format: string; data: string; filename?: string }) {
  await chat.submit(query, structure)
}

function onLogout() {
  auth.logout()
  session.clear()
  chat.clear()
  conversation.newConversation()
  router.push({ name: 'login' })
}

watch(
  () => [chat.messages.length, chat.isRunning, chat.messages.map((m) => m.blocks.length).join(',')],
  () => {
    nextTick(() => {
      if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
    })
  },
)
</script>

<style scoped>
.chat-view {
  height: 100%;
  display: flex;
}

.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.chat {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  align-items: center;
}

.empty {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-secondary);
  margin-top: 60px;
}
.empty .icon {
  font-size: 48px;
  margin-bottom: 16px;
}
.empty .title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
}
.empty .sub {
  font-size: 13px;
}
</style>
