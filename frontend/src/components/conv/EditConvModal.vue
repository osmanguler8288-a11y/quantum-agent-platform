<template>
  <div v-if="visible && conv" class="overlay" @click.self="close">
    <div class="modal">
      <div class="modal-header">
        <div class="modal-icon">✓</div>
        <div class="header-text">
          <div class="modal-title">编辑对话</div>
          <div class="header-sub">「{{ conv.title }}」</div>
        </div>
        <button class="close" @click="close">×</button>
      </div>

      <div class="modal-body">
        <label class="field">
          <span class="label">对话标题 <b>*</b></span>
          <input v-model="form.title" type="text" placeholder="对话标题" />
        </label>

        <div class="field">
          <span class="label">标签 <span class="hint">（最多 5 个，回车添加）</span></span>
          <div class="tag-editor">
            <span v-for="(t, i) in form.tags" :key="t + i" class="tag">
              {{ t }}<button type="button" @click="form.tags.splice(i, 1)">×</button>
            </span>
            <input
              v-model="tagDraft"
              class="tag-input"
              placeholder="回车添加…"
              @keydown.enter.prevent="addTag"
            />
          </div>
        </div>

        <div class="bool-grid">
          <div class="bool-row">
            <div class="ico">📌</div>
            <div class="text">
              <div class="t">置顶</div>
              <div class="d">固定在列表顶部</div>
            </div>
            <div class="switch-track" :class="{ on: form.pinned }" @click="form.pinned = !form.pinned" />
          </div>
          <div class="bool-row">
            <div class="ico archive">🗄</div>
            <div class="text">
              <div class="t">归档</div>
              <div class="d">从默认列表移至归档</div>
            </div>
            <div class="switch-track" :class="{ on: form.archived }" @click="form.archived = !form.archived" />
          </div>
        </div>

        <!-- 只读元信息：单行，绝不折行 -->
        <div class="meta-strip">
          <div class="item">📅 <b>{{ formatRelativeTime(conv.created_at) }}</b>创建</div>
          <div class="item">💬 <b>{{ conv.message_count }} 条</b>消息</div>
          <div class="item">🕒 <b>{{ formatRelativeTime(conv.updated_at) }}</b>活动</div>
          <div class="item">✦ <b>{{ modelLabel(conv.model) }}</b></div>
        </div>
      </div>

      <div v-if="error" class="error-bar">{{ error }}</div>

      <div class="modal-footer">
        <button class="btn-left" @click="$emit('remove', conv)">🗑 删除对话</button>
        <div class="btn-right">
          <button class="btn btn-ghost" @click="close">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="submit">
            {{ saving ? '保存中…' : '保存修改' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import {
  formatRelativeTime, modelLabel, setConversationFlags, updateConversation,
  type ConvSummary,
} from '@/api/conversation'

const props = defineProps<{ visible: boolean; conv: ConvSummary | null }>()
const emit = defineEmits<{
  (e: 'close'): void
  /** 保存成功 → 回传最新的会话摘要（供侧边栏同步标题/归档状态） */
  (e: 'saved', conv: ConvSummary): void
  (e: 'remove', conv: ConvSummary): void
}>()

const form = reactive({
  title: '',
  tags: [] as string[],
  pinned: false,
  archived: false,
})
const tagDraft = ref('')
const saving = ref(false)
const error = ref('')

watch(
  () => [props.visible, props.conv] as const,
  ([visible, conv]) => {
    if (!visible || !conv) return
    form.title = conv.title
    form.tags = [...conv.tags]
    form.pinned = conv.pinned
    form.archived = conv.archived || conv.status === 'archived'
    tagDraft.value = ''
    error.value = ''
  },
  { immediate: true },
)

function addTag() {
  const t = tagDraft.value.trim()
  if (t && !form.tags.includes(t) && form.tags.length < 5) form.tags.push(t)
  tagDraft.value = ''
}

async function submit() {
  const conv = props.conv
  if (!conv) return
  error.value = ''
  if (!form.title.trim()) return (error.value = '请填写对话标题')
  saving.value = true
  try {
    const updated = await updateConversation(conv.id, {
      title: form.title.trim(),
      tags: form.tags,
    })
    // 开关只在有变化时才发请求（乐观语义：不变不 PATCH）
    if (form.pinned !== conv.pinned || form.archived !== (conv.archived || conv.status === 'archived')) {
      await setConversationFlags(conv.id, { pinned: form.pinned, archived: form.archived })
    }
    // 回传本地最新状态（后端返回值可能不含刚改的开关）
    emit('saved', {
      ...updated,
      title: form.title.trim(),
      tags: [...form.tags],
      pinned: form.pinned,
      archived: form.archived,
      status: form.archived ? 'archived' : updated.status,
    })
    close()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    saving.value = false
  }
}

function close() {
  emit('close')
}
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(28, 25, 23, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
}
.modal {
  width: 480px;
  max-width: 100%;
  max-height: 90vh;
  background: var(--surface);
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 22px 14px;
  border-bottom: 1px solid var(--border);
}
.modal-icon {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: var(--green-bg);
  color: var(--green-text);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  flex-shrink: 0;
}
.header-text { flex: 1; min-width: 0; }
.modal-title { font-size: 16px; font-weight: 700; }
.header-sub {
  font-size: 11.5px;
  color: var(--text-secondary);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.close {
  width: 28px;
  height: 28px;
  border: none;
  background: none;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 16px;
  flex-shrink: 0;
}
.close:hover { background: #f5f5f4; color: var(--text); }

.modal-body {
  padding: 16px 22px 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
}
.field { display: flex; flex-direction: column; gap: 6px; }
.label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 6px;
}
.label b { color: var(--red-text); font-weight: 600; }
.hint { font-size: 11px; color: var(--text-secondary); font-weight: 400; }

input {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 13px;
  color: var(--text);
  font-family: inherit;
  width: 100%;
  outline: none;
  transition: border-color 0.15s;
}
input:focus { border-color: var(--orange); }

.tag-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 6px 8px 6px 10px;
  background: var(--surface);
  transition: border-color 0.15s;
}
.tag-editor:focus-within { border-color: var(--orange); }
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  padding: 2px 7px;
  border-radius: 7px;
  background: var(--orange-light);
  color: var(--orange-hover);
  font-weight: 600;
}
.tag button {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 11px;
  color: var(--orange-hover);
  opacity: 0.7;
  padding: 0;
  line-height: 1;
}
.tag button:hover { opacity: 1; }
.tag-input {
  flex: 1;
  min-width: 80px;
  border: none;
  outline: none;
  background: none;
  font-size: 12.5px;
  padding: 4px 0;
  font-family: inherit;
  width: auto;
}
.tag-input:focus { border: none; }

.bool-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.bool-row {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.bool-row .ico {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  background: var(--orange-light);
  color: var(--orange);
  flex-shrink: 0;
}
.bool-row .ico.archive { background: #f5f5f4; color: var(--text-secondary); }
.bool-row .text { flex: 1; min-width: 0; }
.bool-row .t { font-size: 12.5px; font-weight: 600; }
.bool-row .d { font-size: 11px; color: var(--text-secondary); margin-top: 1px; }
.switch-track {
  width: 34px;
  height: 20px;
  border-radius: 10px;
  background: #d6d3d1;
  position: relative;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}
.switch-track.on { background: var(--orange); }
.switch-track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: left 0.15s;
}
.switch-track.on::after { left: 16px; }

.meta-strip {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 11.5px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: nowrap;
  justify-content: space-between;
}
.meta-strip .item {
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.meta-strip .item b { color: var(--text); font-weight: 700; }

.error-bar {
  margin: 8px 22px 0;
  padding: 9px 12px;
  background: var(--red-bg);
  border: 1px solid var(--red-border);
  border-radius: 10px;
  color: var(--red-text);
  font-size: 12.5px;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 22px 18px;
  border-top: 1px solid var(--border);
  background: var(--bg);
  margin-top: 8px;
}
.btn-left {
  background: none;
  border: none;
  padding: 8px 12px;
  font-size: 12.5px;
  color: var(--red-text);
  cursor: pointer;
  font-weight: 600;
  border-radius: 8px;
  font-family: inherit;
}
.btn-left:hover { background: var(--red-bg); }
.btn-right { display: flex; gap: 10px; }
.btn {
  border: none;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.15s;
  font-family: inherit;
  padding: 10px 20px;
  font-size: 13px;
}
.btn-primary { background: var(--orange); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--orange-hover); }
.btn-primary:disabled { opacity: 0.6; cursor: wait; }
.btn-ghost { background: transparent; color: var(--text); border: 1px solid var(--border); }
.btn-ghost:hover { background: #f5f5f4; }
</style>
