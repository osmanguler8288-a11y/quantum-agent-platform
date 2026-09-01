<template>
  <div class="msg" :class="message.role">
    <div class="avatar">{{ message.role === 'user' ? 'U' : 'A' }}</div>
    <div class="bubble">
      <template v-if="message.role === 'user'">
        <template v-for="(block, i) in message.blocks" :key="i">
          <span v-if="block.type === 'text'" class="user-text">{{ block.text }}</span>
        </template>
      </template>

      <template v-else>
        <template v-for="(block, i) in message.blocks" :key="i">
          <ThinkingBlock v-if="block.type === 'thinking'" :text="block.text" />
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
