<template>
  <div class="verdict" :class="verdict.passed ? 'pass' : 'fail'">
    <div v-if="verdict.comment" class="v-comment">{{ verdict.comment }}</div>
    <div class="v-header">
      <span class="icon">{{ verdict.passed ? '✓' : '⚠' }}</span>
      <span>{{ verdict.passed ? 'PASS — 结果验证通过' : 'FAIL — 结果验证未通过' }}</span>
    </div>
    <div v-if="verdict.reason" class="v-reason">{{ verdict.reason }}</div>
    <div v-if="verdict.suggestions" class="v-suggest">建议: {{ verdict.suggestions }}</div>
  </div>
</template>

<script setup lang="ts">
import type { Verdict } from '@/types'

defineProps<{ verdict: Verdict }>()
</script>

<style scoped>
.verdict {
  padding: 12px 14px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
}
.verdict.pass {
  background: var(--green-bg);
  border: 1px solid var(--green-border);
}
.verdict.fail {
  background: var(--amber-bg);
  border: 1px solid var(--amber-border);
}

.v-comment {
  white-space: pre-wrap;
  margin-bottom: 8px;
}

.v-header {
  font-weight: 700;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.v-header .icon {
  font-size: 16px;
}

.v-reason {
  color: var(--text-secondary);
  margin-top: 4px;
}

.v-suggest {
  margin-top: 6px;
  font-size: 12px;
  color: var(--orange);
}
</style>
