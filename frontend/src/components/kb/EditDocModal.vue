<template>
  <div v-if="visible && doc" class="overlay" @click.self="close">
    <div class="modal">
      <div class="modal-header">
        <div class="doc-icon" :class="icon.cls">{{ icon.emoji }}</div>
        <div class="header-info">
          <h3>编辑文档 · {{ doc.name }}</h3>
          <div class="header-sub">
            {{ formatSize(doc.size_bytes) }} · {{ chunkText }} · {{ statusText }} · 上传于 {{ formatShortDate(doc.created_at) }}
          </div>
        </div>
        <button class="close" @click="close">×</button>
      </div>

      <div class="body">
        <label class="field">
          <span class="label">文档名称 <b>*</b></span>
          <input v-model="form.name" class="name-input" placeholder="含扩展名的文件名" />
        </label>

        <div class="field-row">
          <label class="field grow">
            <span class="label">分类 <b>*</b></span>
            <select v-model="form.category">
              <option v-for="c in categoryNames" :key="c" :value="c">{{ c }}</option>
            </select>
          </label>
          <div class="field grow">
            <span class="label">替换源文件</span>
            <button type="button" class="replace-btn" @click="fileInput?.click()">
              {{ replaceFile ? `已选择：${replaceFile.name}` : '点击选择新文件（可选）' }}
            </button>
            <input ref="fileInput" type="file" hidden @change="onReplaceFile" />
          </div>
        </div>

        <div class="field">
          <span class="label">标签</span>
          <div class="tag-editor">
            <span v-for="(t, i) in form.tags" :key="t + i" class="tag">
              {{ t }}<button type="button" @click="form.tags.splice(i, 1)">×</button>
            </span>
            <input
              v-model="tagDraft"
              class="tag-input"
              placeholder="输入后回车添加"
              @keydown.enter.prevent="addTag"
            />
          </div>
        </div>

        <label class="field">
          <span class="label">描述</span>
          <textarea v-model="form.description" rows="3" placeholder="将作为元数据参与检索匹配" />
        </label>

        <div class="toggle-bar">
          <div class="switch-track" :class="{ on: form.searchable }" @click="form.searchable = !form.searchable" />
          <div class="toggle-text">
            <b>参与检索</b> — 关闭后该文档的分块将从检索候选中排除，但不会被删除
          </div>
        </div>

        <div class="rebuild-hint">
          <span class="hint-text">修改名称 / 描述 / 标签后需重建索引，才能反映到检索结果中</span>
          <button class="btn btn-ghost btn-rebuild" :disabled="saving" @click="submit(true)">
            {{ saving ? '处理中…' : '保存并重建索引' }}
          </button>
        </div>
      </div>

      <div v-if="error" class="error-bar">{{ error }}</div>

      <div class="modal-footer">
        <button class="btn btn-ghost" @click="close">取消</button>
        <button class="btn btn-primary" :disabled="saving" @click="submit(false)">
          {{ saving ? '保存中…' : '保存修改' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  CATEGORY_ICON, CATEGORY_NAMES, formatShortDate, formatSize, reindexKbDoc, updateKbDoc,
  type KbDoc,
} from '@/api/kb'

const props = defineProps<{ visible: boolean; doc: KbDoc | null }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()

const categoryNames = CATEGORY_NAMES

const form = reactive({
  name: '',
  category: '' as string,
  tags: [] as string[],
  description: '',
  searchable: true,
})
const tagDraft = ref('')
const replaceFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const saving = ref(false)
const error = ref('')

const icon = computed(() => CATEGORY_ICON[props.doc?.category ?? ''] ?? { cls: 'pdf', emoji: '📄' })
const chunkText = computed(() =>
  props.doc?.chunk_count === null || props.doc?.chunk_count === undefined
    ? '— 块'
    : `${props.doc.chunk_count.toLocaleString('zh-CN')} 个分块`,
)
const statusText = computed(() => ({
  indexed: '已索引',
  indexing: '索引中',
  failed: '索引失败',
}[props.doc?.index_status ?? 'indexed']))

watch(
  () => [props.visible, props.doc] as const,
  ([visible, doc]) => {
    if (!visible || !doc) return
    form.name = doc.name
    form.category = doc.category
    form.tags = [...doc.tags]
    form.description = doc.description
    form.searchable = doc.searchable
    tagDraft.value = ''
    replaceFile.value = null
    error.value = ''
  },
  { immediate: true },
)

function onReplaceFile(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) replaceFile.value = input.files[0]
  input.value = ''
}

function addTag() {
  const t = tagDraft.value.trim()
  if (t && !form.tags.includes(t)) form.tags.push(t)
  tagDraft.value = ''
}

async function submit(withReindex: boolean) {
  if (!props.doc) return
  error.value = ''
  if (!form.name.trim()) return (error.value = '请填写文档名称')
  saving.value = true
  try {
    await updateKbDoc(props.doc.id, {
      name: form.name.trim(),
      category: form.category,
      tags: form.tags,
      description: form.description.trim(),
      searchable: form.searchable,
    })
    if (withReindex) {
      await reindexKbDoc(props.doc.id)
    }
    emit('saved')
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
  width: 600px;
  max-width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.header-info { flex: 1; min-width: 0; }
.header-info h3 {
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.header-sub { font-size: 11px; color: var(--text-secondary); margin-top: 2px; }
.close {
  border: none;
  background: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text-secondary);
  line-height: 1;
  flex-shrink: 0;
}
.close:hover { color: var(--text); }

.doc-icon {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 19px;
  flex-shrink: 0;
}
.doc-icon.pdf { background: var(--red-bg); color: var(--red-text); }
.doc-icon.md { background: var(--amber-bg); color: var(--amber-text); }
.doc-icon.data { background: var(--green-bg); color: var(--green-text); }
.doc-icon.sop { background: var(--purple-bg); color: var(--purple-text); }

.body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field { display: flex; flex-direction: column; gap: 6px; }
.field-row { display: flex; gap: 14px; }
.field.grow { flex: 1; }
.label { font-size: 12.5px; font-weight: 600; color: var(--text); }
.label b { color: var(--orange); }

input,
select,
textarea {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 13px;
  font-family: inherit;
  color: var(--text);
  background: var(--surface);
  outline: none;
  width: 100%;
}
input:focus,
select:focus,
textarea:focus { border-color: var(--orange); }
/* 与设计稿一致：名称输入框聚焦时高亮为琥珀色 */
.name-input:focus {
  border-color: var(--orange-border);
  background: var(--orange-light);
}
textarea { resize: vertical; line-height: 1.5; }

.replace-btn {
  border: 1px dashed var(--border);
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 12.5px;
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--surface);
  font-family: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: center;
}
.replace-btn:hover { border-color: var(--orange); color: var(--orange); }

.tag-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 7px 10px;
  min-height: 40px;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 2px 6px 2px 8px;
  border-radius: 6px;
  color: var(--text-secondary);
}
.tag button {
  border: none;
  background: none;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1;
  padding: 0;
}
.tag button:hover { color: var(--red-text); }
.tag-input {
  border: none;
  outline: none;
  flex: 1;
  min-width: 90px;
  font-size: 12.5px;
  padding: 4px 0;
  background: transparent;
  color: var(--text);
  font-family: inherit;
  width: auto;
}
.tag-input:focus { border: none; }

.toggle-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--amber-border);
  background: var(--amber-bg);
  border-radius: 10px;
}
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
.toggle-text { font-size: 12.5px; color: var(--amber-text); }

.rebuild-hint {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid var(--border);
  background: var(--bg);
  border-radius: 10px;
  font-size: 12px;
  color: var(--text-secondary);
}
.hint-text { flex: 1; }
.btn-rebuild { padding: 6px 14px; font-size: 12px; flex-shrink: 0; }

.error-bar {
  margin: 8px 20px 0;
  padding: 9px 12px;
  background: var(--red-bg);
  border: 1px solid var(--red-border);
  border-radius: 10px;
  color: var(--red-text);
  font-size: 12.5px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}
.btn { padding: 10px 22px; font-size: 13px; }
.btn-ghost { background: #f5f5f4; color: var(--text); }
.btn-ghost:hover:not(:disabled) { background: #e7e5e4; }
</style>
