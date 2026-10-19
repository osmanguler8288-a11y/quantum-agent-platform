<template>
  <div class="input-bar">
    <div class="input-inner">
      <button
        class="struct-btn"
        :class="{ attached: !!pendingStructure }"
        title="输入分子结构"
        @click="showStructure = true"
      >
        ⌬ 结构
      </button>
      <input
        v-model="query"
        type="text"
        placeholder="描述你的计算化学任务..."
        :disabled="isRunning"
        @keydown.enter="submit"
      />
      <button
        class="btn btn-primary send"
        :disabled="isRunning || (!query.trim() && !pendingStructure)"
        @click="submit"
      >
        <span v-if="isRunning" class="spinner"></span>{{ isRunning ? 'Running' : 'Send' }}
      </button>
    </div>

    <!-- 已挂附件。⚠️ 必须有这一条：确认弹窗一关，附件在界面上就完全不可见了，
         用户既不知道挂上了什么，也无从撤销。 -->
    <div v-if="pendingStructure" class="attach-chip">
      <span class="ac-icon">⌬</span>
      <span class="ac-name">{{ pendingStructure.filename || 'XYZ 结构' }}</span>
      <span class="ac-kind">{{ pendingStructure.format === 'file' ? '文件' : 'XYZ 文本' }}</span>
      <button class="ac-remove" title="移除附件" @click="pendingStructure = undefined">×</button>
    </div>

    <SuggestionChips @select="fill" />

    <StructureInput :visible="showStructure" @close="showStructure = false" @confirm="onStructure" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import SuggestionChips from './SuggestionChips.vue'
import StructureInput from './StructureInput.vue'
import type { StructurePayload } from '@/types'

const props = defineProps<{ isRunning: boolean }>()
const emit = defineEmits<{
  (e: 'submit', query: string, structure?: StructurePayload): void
}>()

const query = ref('')
const showStructure = ref(false)
const pendingStructure = ref<StructurePayload>()

/**
 * 跨页预填草稿：技能中心「在对话中试用」等入口通过 sessionStorage 留一句调用话术，
 * 挂载时取一次并立即清掉，避免刷新后重复出现。
 */
const CHAT_DRAFT_KEY = 'qap_chat_draft'
onMounted(() => {
  const draft = sessionStorage.getItem(CHAT_DRAFT_KEY)
  if (draft) {
    query.value = draft
    sessionStorage.removeItem(CHAT_DRAFT_KEY)
  }
})

function fill(text: string) {
  query.value = text
}

function submit() {
  // 只挂附件、没打字也要能发出去
  if ((!query.value.trim() && !pendingStructure.value) || props.isRunning) return
  emit('submit', query.value.trim(), pendingStructure.value)
  pendingStructure.value = undefined
  query.value = ''
}

function onStructure(s: StructurePayload) {
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
/* 挂了附件时按钮常亮 —— 用户不展开也知道挂着东西 */
.struct-btn.attached {
  border-color: var(--orange);
  color: var(--orange);
  background: rgba(254, 243, 199, 0.55);
}

/* ── 已挂附件条 ── */
.attach-chip {
  max-width: 820px;
  margin: 8px auto 0;
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  padding: 6px 8px 6px 12px;
  background: rgba(254, 243, 199, 0.45);
  border: 1px solid var(--orange-border);
  border-radius: 10px;
  font-size: 12.5px;
}
.ac-icon {
  color: var(--orange);
}
.ac-name {
  font-weight: 600;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ac-kind {
  color: var(--text-secondary);
  font-size: 11.5px;
}
.ac-remove {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0 4px;
  color: var(--text-secondary);
}
.ac-remove:hover {
  color: var(--red-text);
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
