<template>
  <div class="thinking">
    <div class="thinking-header" @click="collapsed = !collapsed">
      <span class="arrow">{{ collapsed ? '▸' : '▾' }}</span>
      <span class="label">THINKING</span>
      <span class="hint">{{ collapsed ? '展开思考过程' : '点击折叠' }}</span>
    </div>
    <div v-show="!collapsed" class="thinking-body">{{ text }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ text: string }>()

const collapsed = ref(false)
</script>

<style scoped>
.thinking {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: #fafaf9;
}

.thinking-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 11px;
}
.thinking-header:hover {
  background: #f5f5f4;
}

.arrow {
  color: var(--text-secondary);
  font-size: 12px;
}

.label {
  font-weight: 700;
  color: var(--orange);
  letter-spacing: 0.5px;
}

.hint {
  margin-left: auto;
  color: var(--text-secondary);
  font-size: 11px;
}

.thinking-body {
  padding: 10px 12px;
  color: var(--text-secondary);
  font-size: 13px;
  white-space: pre-wrap;
  border-top: 1px solid var(--border);
}
</style>
