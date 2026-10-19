<template>
  <div class="msg" :class="message.role">
    <div class="avatar">{{ message.role === 'user' ? 'U' : 'A' }}</div>
    <div class="bubble">
      <template v-if="message.role === 'user'">
        <!-- ⚠️ 用户分支是逐块 v-if，不处理就会**静默消失** —— 只挂附件、
             没打字时 blocks 里只有 attachment 块，漏了这一支用户气泡会是空的。 -->
        <template v-for="(block, i) in message.blocks" :key="i">
          <span v-if="block.type === 'text'" class="user-text">{{ block.text }}</span>
          <div
            v-else-if="block.type === 'attachment'"
            class="user-attachment"
            :class="block.status"
            :title="block.path || block.filename"
          >
            <span class="ua-icon">⌬</span>
            <span class="ua-name">{{ block.filename }}</span>
            <span v-if="block.status === 'pending'" class="ua-meta">解析中…</span>
            <span v-else-if="block.status === 'failed'" class="ua-meta ua-fail">解析失败</span>
            <span v-else class="ua-meta">{{ block.natoms }} 原子 · {{ block.formula }}</span>
            <span v-if="block.path" class="ua-path">{{ block.path }}</span>
          </div>
        </template>
      </template>

      <template v-else>
        <template v-for="(block, i) in message.blocks" :key="i">
          <!-- ⚠️ assistant 分支必须有 text —— 从后端回填的历史消息就是纯文本块
               （见 stores/chat.ts 的 loadConversation）。少了这一支，
               点开历史对话时用户提问能看到、助手回复却是空白。 -->
          <div v-if="block.type === 'text'" class="assistant-text">{{ block.text }}</div>
          <ThinkingBlock v-else-if="block.type === 'thinking'" :text="block.text" />
          <PlanCard v-else-if="block.type === 'plan'" :plan="block.plan" />
          <StepList v-else-if="block.type === 'steps'" :steps="block.steps" />
          <ResultViz v-else-if="block.type === 'viz'" :viz="block.viz" />
          <VerdictCard v-else-if="block.type === 'verdict'" :verdict="block.verdict" />
          <RetryBanner v-else-if="block.type === 'retry'" :retry-count="block.retryCount" />
          <div v-else-if="block.type === 'error'" class="error-block">{{ block.message }}</div>
          <div v-else-if="block.type === 'done'" class="done-block">
            {{ block.status === 'passed' ? '任务完成 ✓' : '达到最大重试次数' }}
          </div>
        </template>

        <!-- 流式进行中的占位光标 -->
        <span v-if="message.role === 'assistant' && isRunning" class="cursor">▍</span>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ChatMessage } from '@/types'
import ThinkingBlock from './ThinkingBlock.vue'
import PlanCard from './PlanCard.vue'
import StepList from './StepList.vue'
import ResultViz from './viz/ResultViz.vue'
import VerdictCard from './VerdictCard.vue'
import RetryBanner from './RetryBanner.vue'

defineProps<{ message: ChatMessage; isRunning?: boolean }>()
</script>

<style scoped>
.msg {
  display: flex;
  gap: 14px;
  max-width: 820px;
  width: 100%;
  animation: fadeIn 0.3s ease-out;
}
.msg.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.msg.assistant {
  align-self: flex-start;
}

.avatar {
  width: 30px;
  height: 30px;
  border-radius: 6px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  margin-top: 2px;
}
.msg.user .avatar {
  background: var(--orange);
}
.msg.assistant .avatar {
  background: #44403c;
}

.bubble {
  padding: 14px 18px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.65;
  max-width: 100%;
  overflow-wrap: break-word;
}
.msg.user .bubble {
  background: #f5f5f4;
  border-bottom-right-radius: 4px;
}
.msg.assistant .bubble {
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.user-text {
  white-space: pre-wrap;
}

/* ── 用户消息上的分子结构附件 ──
   气泡底色是 #f5f5f4，chip 用白底才跳得出来（与 kb/UploadDocsModal 的 .file-item 同型） */
.user-attachment {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  max-width: 100%;
  margin-top: 6px;
  padding: 6px 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--orange);
  border-radius: 10px;
  font-size: 12.5px;
}
.user-attachment.failed {
  border-left-color: var(--red-text);
}
.ua-icon {
  color: var(--orange);
  flex-shrink: 0;
}
.user-attachment.failed .ua-icon {
  color: var(--red-text);
}
.ua-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ua-meta {
  color: var(--text-secondary);
  flex-shrink: 0;
}
.ua-fail {
  color: var(--red-text);
}
.ua-path {
  color: var(--text-secondary);
  font-size: 11px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
  padding-left: 4px;
  border-left: 1px solid var(--border);
  margin-left: 2px;
}

/* 历史回填的助手回复（纯文本块）——与流式时的 ThinkingBlock 区分开，
   这里展示的是**已落库的最终答复**，不是过程中的推理 */
.assistant-text {
  white-space: pre-wrap;
  line-height: 1.7;
  font-size: 13.5px;
  color: var(--text);
}

.error-block {
  color: var(--red-text);
  background: var(--red-bg);
  border: 1px solid var(--red-border);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
}

.done-block {
  color: var(--green-text);
  font-size: 13px;
  font-weight: 600;
}

.cursor {
  color: var(--orange);
  animation: blink 0.8s infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
