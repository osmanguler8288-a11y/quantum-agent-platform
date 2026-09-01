<template>
  <div class="steps">
    <div class="label">EXECUTING</div>
    <div class="step-list">
      <div v-for="s in steps" :key="s.index" class="step-row" :class="s.status">
        <div class="dot" :class="s.status"></div>
        <span class="step-idx">Step {{ s.index + 1 }}</span>
        <span class="step-tool">{{ s.step?.step || s.result?.tool || '' }}</span>
        <span class="step-status" :class="s.status">
          {{ s.status === 'running' ? 'running...' : s.status === 'done' ? 'success' : 'error' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StepStatus } from '@/types'

defineProps<{ steps: StepStatus[] }>()
</script>

<style scoped>
.label {
  font-size: 11px;
  font-weight: 600;
  color: var(--orange);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.step-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  border: 1px solid transparent;
}
.step-row.done {
  background: var(--green-bg);
  border-color: var(--green-border);
}
.step-row.fail {
  background: var(--red-bg);
  border-color: var(--red-border);
}
.step-row.running {
  background: #fafaf9;
  border-color: var(--border);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot.done {
  background: #22c55e;
}
.dot.fail {
  background: #ef4444;
}
.dot.running {
  background: var(--orange);
  animation: pulse 1s infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.4;
  }
}

.step-idx {
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 45px;
}

.step-tool {
  font-weight: 500;
}

.step-status {
  margin-left: auto;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.step-status.done {
  background: #dcfce7;
  color: var(--green-text);
}
.step-status.fail {
  background: #fee2e2;
  color: var(--red-text);
}
.step-status.running {
  background: var(--orange-light);
  color: var(--amber-text);
}
</style>
