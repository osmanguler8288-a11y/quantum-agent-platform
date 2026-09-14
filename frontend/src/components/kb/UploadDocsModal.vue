<template>
  <div v-if="visible" class="overlay" @click.self="close">
    <div class="modal">
      <div class="modal-header">
        <h3>上传文档到知识库</h3>
        <button class="close" @click="close">×</button>
      </div>
      <p class="hint">
        支持 PDF / Word / Markdown / TXT / CSV，单文件 ≤ 50 MB。上传后自动分块并向量化，索引完成后即可被 Agent 检索。
      </p>

      <div class="body">
        <!-- 拖拽区 -->
        <div
          class="dropzone"
          :class="{ dragover }"
          @click="fileInput?.click()"
          @dragover.prevent="dragover = true"
          @dragleave.prevent="dragover = false"
          @drop.prevent="onDrop"
        >
          <div class="dz-icon">⬆</div>
          <div class="dz-title">点击选择文件，或将文件拖拽到此处</div>
          <div class="dz-sub">支持批量上传，同名文件将自动覆盖旧版本</div>
        </div>
        <input ref="fileInput" type="file" multiple hidden @change="onFileChange" />

        <!-- 已选文件 -->
        <div v-if="files.length" class="field">
          <div class="label">已选择 {{ files.length }} 个文件</div>
          <div class="file-list">
            <div v-for="(f, i) in files" :key="f.name + i" class="file-item">
              <span class="f-icon">📄</span>
              <span class="f-name">{{ f.name }}</span>
              <span class="f-meta">{{ formatSize(f.size) }}</span>
              <span class="badge" :class="badgeCls">{{ category }}</span>
              <button class="f-remove" title="移除" @click="files.splice(i, 1)">×</button>
            </div>
          </div>
        </div>

        <!-- 元数据 -->
        <div class="field-row">
          <label class="field grow">
            <span class="label">分类 <b>*</b></span>
            <select v-model="category">
              <option v-for="c in categoryNames" :key="c" :value="c">{{ c }}</option>
            </select>
          </label>
          <div class="field" style="width: 240px">
            <span class="label">标签</span>
            <div class="tag-editor">
              <span v-for="(t, i) in tags" :key="t + i" class="tag">
                {{ t }}<button type="button" @click="tags.splice(i, 1)">×</button>
              </span>
              <input
                v-model="tagDraft"
                class="tag-input"
                placeholder="输入后回车添加"
                @keydown.enter.prevent="addTag"
              />
            </div>
          </div>
        </div>

        <label class="field">
          <span class="label">描述</span>
          <textarea v-model="description" rows="2" placeholder="补充说明（可选），将作为元数据参与检索匹配…" />
        </label>

        <!-- 分块策略 -->
        <div class="field">
          <span class="label">分块策略</span>
          <div class="strategy-row">
            <div class="segmented">
              <button
                v-for="(label, key) in strategyLabels"
                :key="key"
                type="button"
                :class="{ on: strategy === key }"
                @click="strategy = key"
              >{{ label }}</button>
            </div>
            <div class="chunk-limit">
              <span class="cl-label">分块上限</span>
              <div class="limit-select" @click="limitOpen = !limitOpen">
                <span>{{ chunkLimit }}</span>
                <span class="cl-unit">tokens ▾</span>
              </div>
              <div v-if="limitOpen" class="limit-menu">
                <button v-for="v in [256, 512, 1024]" :key="v" type="button" @click="chunkLimit = v; limitOpen = false">{{ v }} tokens</button>
              </div>
            </div>
            <span class="overlap-hint">Overlap 默认 64</span>
          </div>
        </div>

        <div class="toggle-bar">
          <div class="switch-track" :class="{ on: searchableAfterIndex }" @click="searchableAfterIndex = !searchableAfterIndex" />
          <div class="toggle-text">
            <b>索引完成后立即可被检索</b> — 关闭后文档仅存储，可稍后在列表中手动开启
          </div>
        </div>
      </div>

      <div v-if="error" class="error-bar">{{ error }}</div>

      <div class="modal-footer">
        <button class="btn btn-ghost" @click="close">取消</button>
        <button class="btn btn-primary" :disabled="saving" @click="submit">
          {{ saving ? '上传中…' : files.length ? `开始上传并索引（${files.length} 个文件）` : '开始上传并索引' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  CATEGORY_BADGE, CATEGORY_NAMES, CHUNK_STRATEGY_LABELS, formatSize, uploadKbDocs,
  type ChunkStrategy,
} from '@/api/kb'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()

const strategyLabels = CHUNK_STRATEGY_LABELS
const categoryNames = CATEGORY_NAMES

const fileInput = ref<HTMLInputElement | null>(null)
const files = ref<{ name: string; size: number }[]>([])
const dragover = ref(false)
const category = ref<string>(CATEGORY_NAMES[0])
const tags = ref<string[]>([])
const tagDraft = ref('')
const description = ref('')
const strategy = ref<ChunkStrategy>('paragraph')
const chunkLimit = ref(512)
const limitOpen = ref(false)
const searchableAfterIndex = ref(true)
const saving = ref(false)
const error = ref('')

const badgeCls = computed(() => CATEGORY_BADGE[category.value] ?? 'sop')

watch(
  () => props.visible,
  (v) => {
    if (v) {
      files.value = []
      tags.value = []
      tagDraft.value = ''
      description.value = ''
      category.value = CATEGORY_NAMES[0]
      strategy.value = 'paragraph'
      chunkLimit.value = 512
      searchableAfterIndex.value = true
      error.value = ''
    }
  },
)

function addFiles(list: FileList | File[]) {
  const MAX_SIZE = 50 * 1024 * 1024
  for (const f of Array.from(list)) {
    if (f.size > MAX_SIZE) {
      error.value = `「${f.name}」超过 50 MB 上限，已跳过`
      continue
    }
    // 同名覆盖：去掉旧的同名条目
    files.value = files.value.filter((x) => x.name !== f.name)
    files.value.push({ name: f.name, size: f.size })
  }
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) addFiles(input.files)
  input.value = ''
}

function onDrop(e: DragEvent) {
  dragover.value = false
  if (e.dataTransfer?.files) addFiles(e.dataTransfer.files)
}

function addTag() {
  const t = tagDraft.value.trim()
  if (t && !tags.value.includes(t)) tags.value.push(t)
  tagDraft.value = ''
}

async function submit() {
  error.value = ''
  if (!files.value.length) return (error.value = '请先选择要上传的文件')
  saving.value = true
  try {
    await uploadKbDocs({
      files: files.value,
      category: category.value,
      tags: tags.value,
      description: description.value.trim(),
      strategy: strategy.value,
      chunk_limit: chunkLimit.value,
      searchable: searchableAfterIndex.value,
    })
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
  width: 640px;
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
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.modal-header h3 { font-size: 16px; }
.close {
  border: none;
  background: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text-secondary);
  line-height: 1;
}
.close:hover { color: var(--text); }

.hint {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
}

.body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dropzone {
  border: 2px dashed var(--orange-border);
  border-radius: 14px;
  background: rgba(254, 243, 199, 0.35);
  padding: 26px 20px;
  text-align: center;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.dropzone.dragover {
  background: var(--orange-light);
  border-color: var(--orange);
}
.dz-icon { font-size: 30px; margin-bottom: 6px; }
.dz-title { font-size: 13.5px; font-weight: 600; }
.dz-sub { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }

.file-list { display: flex; flex-direction: column; gap: 6px; }
.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 12px;
}
.f-icon { font-size: 16px; }
.f-name { flex: 1; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.f-meta { color: var(--text-secondary); flex-shrink: 0; }
.badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
  flex-shrink: 0;
}
.badge.lit { background: var(--purple-bg); color: var(--purple-text); }
.badge.note { background: var(--amber-bg); color: var(--amber-text); }
.badge.data { background: var(--green-bg); color: var(--green-text); }
.badge.sop { background: #f5f5f4; color: var(--text-secondary); }
.f-remove {
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  padding: 0 2px;
}
.f-remove:hover { color: var(--red-text); }

.field-row { display: flex; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field.grow { flex: 1; }
.label { font-size: 12.5px; font-weight: 600; color: var(--text); }
.label b { color: var(--orange); }

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
select:focus,
textarea:focus { border-color: var(--orange); }
textarea { resize: vertical; line-height: 1.5; }

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
}

.strategy-row { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
.segmented {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.segmented button {
  border: none;
  background: none;
  padding: 8px 16px;
  font-size: 12.5px;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
}
.segmented button.on {
  background: var(--orange-light);
  color: var(--orange-hover);
  font-weight: 600;
}
.chunk-limit { display: flex; align-items: center; gap: 8px; position: relative; }
.cl-label { font-size: 12.5px; color: var(--text-secondary); }
.limit-select {
  display: flex;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  font-size: 12.5px;
}
.limit-select > span:first-child { padding: 7px 12px; }
.cl-unit {
  padding: 7px 10px;
  font-size: 11px;
  color: var(--text-secondary);
  border-left: 1px solid var(--border);
}
.limit-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 100%;
  transform: translateX(-100%);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  min-width: 110px;
  z-index: 10;
  overflow: hidden;
}
.limit-menu button {
  border: none;
  background: none;
  padding: 8px 12px;
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  color: var(--text);
  font-family: inherit;
}
.limit-menu button:hover { background: #f5f5f4; }
.overlap-hint { font-size: 11.5px; color: var(--text-secondary); }

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
.btn-ghost:hover { background: #e7e5e4; }
</style>
