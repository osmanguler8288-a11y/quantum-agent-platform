<template>
  <div class="input-bar">
    <div class="input-inner">
      <button class="struct-btn" title="输入分子结构" @click="showStructure = true">⌬ 结构</button>
      <input
        v-model="query"
        type="text"
        placeholder="描述你的计算化学任务..."
        :disabled="isRunning"
        @keydown.enter="submit"
      />
      <button class="btn btn-primary send" :disabled="isRunning || !query.trim()" @click="submit">
        <span v-if="isRunning" class="spinner"></span>{{ isRunning ? 'Running' : 'Send' }}
      </button>
    </div>

    <SuggestionChips @select="fill" />

    <StructureInput :visible="showStructure" @close="showStructure = false" @confirm="onStructure" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import SuggestionChips from './SuggestionChips.vue'
import StructureInput from './StructureInput.vue'

const props = defineProps<{ isRunning: boolean }>()
const emit = defineEmits<{
  (e: 'submit', query: string, structure?: { format: string; data: string; filename?: string }): void
}>()

const query = ref('')
const showStructure = ref(false)
const pendingStructure = ref<{ format: string; data: string; filename?: string }>()

function fill(text: string) {
  query.value = text
}

function submit() {
  if (!query.value.trim() || props.isRunning) return
  emit('submit', query.value.trim(), pendingStructure.value)
  pendingStructure.value = undefined
  query.value = ''
}

function onStructure(s: { format: string; data: string; filename?: string }) {
  pendingStructure.value = s
  showStructure.value = false
}
</script>

<style scoped>
.input-bar {
  border-top: 1px solid var(--border);
  background: var(--surface);
  padding: 14px 24px;
  flex-shrink: 0;
}

.input-inner {
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  gap: 10px;
  align-items: center;
}

.struct-btn {
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fafaf9;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.struct-btn:hover {
  border-color: var(--orange);
  color: var(--orange);
}

.input-inner input {
  flex: 1;
  padding: 12px 18px;
  border: 1px solid var(--border);
  border-radius: 12px;
  font-size: 14px;
  outline: none;
  background: #fafaf9;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.input-inner input:focus {
  border-color: var(--orange);
  box-shadow: 0 0 0 3px rgba(217, 119, 6, 0.1);
}
.input-inner input::placeholder {
  color: #a8a29e;
}

.send {
  padding: 12px 22px;
  white-space: nowrap;
}
</style>
