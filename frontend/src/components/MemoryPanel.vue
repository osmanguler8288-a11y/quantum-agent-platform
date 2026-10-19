<template>
  <div v-if="visible" class="overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>长期记忆 · 共 {{ filtered.length }} 条</h3>
        <button class="close" @click="$emit('close')">×</button>
      </div>

      <div class="filters">
        <button
          v-for="t in filterTypes"
          :key="t.value"
          :class="{ active: filter === t.value }"
          @click="filter = t.value"
        >
          {{ t.label }}
        </button>
      </div>

      <div class="list">
        <div v-if="loading" class="empty">加载中…</div>
        <div v-else-if="error" class="empty">{{ error }}</div>
        <div v-else-if="filtered.length === 0" class="empty">暂无记忆，多对话几轮自动积累</div>
        <template v-else>
          <div v-for="(m, i) in filtered" :key="m.id || i" class="item">
            <div class="item-top">
              <span class="type-badge" :class="m.type">{{ typeLabels[m.type] }}</span>
              <span class="imp">重要性 {{ m.importance.toFixed(2) }}</span>
              <span class="ts">{{ formatTime(m.timestamp) }}</span>
            </div>
            <div class="content">{{ m.content }}</div>
          </div>
        </template>
      </div>

      <div class="modal-footer">
        <button class="btn btn-ghost" @click="forget">遗忘低重要性</button>
        <button class="btn btn-ghost" @click="consolidate">整合记忆</button>
        <button class="btn btn-primary" @click="$emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiGet, apiPost } from '@/api/client'
import type { MemoryItem, MemoryType } from '@/types'

const props = defineProps<{ visible: boolean }>()
defineEmits<{ (e: 'close'): void }>()

const filter = ref<MemoryType | 'all'>('all')
const items = ref<MemoryItem[]>([])
const loading = ref(false)
const error = ref('')

const filterTypes: { value: MemoryType | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'working', label: '工作' },
  { value: 'episodic', label: '情景' },
  { value: 'semantic', label: '语义' },
  { value: 'perceptual', label: '感知' },
]

const typeLabels: Record<MemoryType, string> = {
  working: '工作',
  episodic: '情景',
  semantic: '语义',
  perceptual: '感知',
}

interface MemoryDto {
  id?: string
  type: MemoryType
  content: string
  importance: number
  timestamp?: string
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await apiGet<{ items?: MemoryDto[] }>('/api/workflow/history')
    items.value = (data.items ?? []).map((m) => ({
      id: m.id,
      type: m.type,
      content: m.content,
      importance: m.importance,
      timestamp: m.timestamp,
    }))
  } catch (e) {
    error.value = (e as Error).message
    items.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, (v) => { if (v) load() })

const filtered = computed(() => {
  if (filter.value === 'all') return items.value
  return items.value.filter((m) => m.type === filter.value)
})

function formatTime(ts?: string): string {
  if (!ts) return ''
  return ts.replace('T', ' ').slice(0, 16)
}

async function consolidate() {
  try {
    await apiPost('/api/workflow/memory/consolidate', {})
    await load()
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function forget() {
  try {
    await apiPost('/api/workflow/memory/forget', {})
    await load()
  } catch (e) {
    error.value = (e as Error).message
  }
}
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--surface);
  border-radius: 16px;
  width: 560px;
  max-width: 92vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.modal-header h3 {
  font-size: 16px;
}
.close {
  border: none;
  background: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text-secondary);
  line-height: 1;
}

.filters {
  display: flex;
  gap: 6px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
}
.filters button {
  border: 1px solid var(--border);
  background: #fafaf9;
  border-radius: 14px;
  padding: 4px 12px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
}
.filters button.active {
  border-color: var(--orange);
  color: var(--orange);
  background: #fff7ed;
}

.list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.empty {
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
  padding: 24px 0;
}

.item {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}

.item-top {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  margin-bottom: 6px;
}

.type-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 700;
}
.type-badge.working {
  background: #fef3c7;
  color: #92400e;
}
.type-badge.episodic {
  background: #dbeafe;
  color: #1e40af;
}
.type-badge.semantic {
  background: #fce7f3;
  color: #9d174d;
}
.type-badge.perceptual {
  background: #e0e7ff;
  color: #4338ca;
}

.imp {
  color: var(--text-secondary);
}
.ts {
  margin-left: auto;
  color: var(--text-secondary);
}

.content {
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}
.modal-footer .btn {
  padding: 10px 16px;
}
</style>
