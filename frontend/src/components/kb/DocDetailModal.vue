<template>
  <div v-if="visible && doc" class="overlay" @click.self="close">
    <div class="modal">
      <!-- 头部 -->
      <div class="modal-header">
        <div class="doc-icon" :class="icon.cls">{{ icon.emoji }}</div>
        <div class="header-info">
          <div class="doc-name">{{ doc.name }}</div>
          <div class="header-badges">
            <span class="badge" :class="badgeCls">{{ doc.category }}</span>
            <span class="badge" :class="statusCls">{{ statusLabel }}</span>
            <span class="uploaded-by">上传于 {{ formatFullDate(doc.created_at) }} · {{ doc.uploaded_by }}</span>
          </div>
        </div>
        <div class="header-actions">
          <button class="btn btn-ghost" @click="$emit('edit', doc)">编辑</button>
          <button class="btn btn-ghost" :disabled="doc.index_status === 'indexing'" @click="$emit('reindex', doc)">
            重新索引
          </button>
          <button class="close" @click="close">×</button>
        </div>
      </div>

      <!-- 内容 -->
      <div class="body">
        <!-- 索引中：进度提示 -->
        <div v-if="doc.index_status === 'indexing'" class="indexing-banner">
          <div class="progress"><i :style="{ width: (doc.index_progress ?? 1) + '%' }" /></div>
          <span class="progress-text">正在分块并向量化：{{ doc.index_progress ?? 0 }}% · 剩余约 {{ doc.index_remaining_sec ?? '—' }} 秒</span>
        </div>

        <!-- 描述 -->
        <section>
          <div class="sec-title">描述</div>
          <p class="desc">{{ doc.description || '（未填写描述）' }}</p>
          <div class="tag-row">
            <span v-for="t in doc.tags" :key="t" class="tag">{{ t }}</span>
          </div>
        </section>

        <!-- 统计 -->
        <section class="stats-grid">
          <div class="stat">
            <div class="stat-label">分块数</div>
            <div class="stat-value">{{ doc.chunk_count === null ? '—' : doc.chunk_count.toLocaleString('zh-CN') }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">字符数</div>
            <div class="stat-value">{{ formatChars(doc.char_count) }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">文件大小</div>
            <div class="stat-value">{{ formatSize(doc.size_bytes) }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">近 30 天引用</div>
            <div class="stat-value green">{{ doc.citations_30d }} 次</div>
          </div>
        </section>

        <!-- 索引失败原因 -->
        <div v-if="doc.index_status === 'failed'" class="failed-banner">
          解析失败：{{ doc.index_error || '未知原因' }}。修复源文件后在右上角「重新索引」。
        </div>

        <!-- 索引信息 -->
        <section v-if="doc.index_status !== 'failed'">
          <div class="sec-title">索引信息</div>
          <table class="info-table">
            <thead>
              <tr>
                <th>索引模型</th>
                <th>分块策略</th>
                <th>分块上限</th>
                <th>最后索引时间</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="mono">{{ doc.index_model || 'bge-m3' }}</td>
                <td>{{ strategyLabel }}</td>
                <td>{{ doc.chunk_limit }} tokens</td>
                <td class="muted">{{ formatDateTime(doc.last_indexed_at) }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- 分块预览 -->
        <section v-if="doc.chunk_preview?.length">
          <div class="sec-row">
            <span class="sec-title">分块预览</span>
            <span class="sec-sub">显示 {{ doc.chunk_count ?? '—' }} 块中的前 {{ doc.chunk_preview.length }} 块</span>
          </div>
          <div class="chunk-list">
            <div v-for="c in doc.chunk_preview" :key="c.idx" class="chunk">
              <span class="chunk-id">#{{ String(c.idx).padStart(3, '0') }}</span>
              {{ c.text }}
            </div>
          </div>
        </section>
      </div>

      <!-- 底部 -->
      <div class="modal-footer">
        <button class="btn btn-ghost btn-danger-text" @click="$emit('remove', doc)">删除文档</button>
        <button class="btn btn-primary" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import {
  CATEGORY_BADGE, CATEGORY_ICON, CHUNK_STRATEGY_LABELS, fetchKbDoc,
  formatChars, formatDateTime, formatFullDate, formatSize, type KbDoc,
} from '@/api/kb'

const props = defineProps<{ visible: boolean; doc: KbDoc | null }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'edit', doc: KbDoc): void
  (e: 'remove', doc: KbDoc): void
  (e: 'reindex', doc: KbDoc): void
}>()

// 详情拉全量数据（含索引信息与分块预览），失败时退回列表里的基础数据
const full = ref<KbDoc | null>(null)
watch(
  () => [props.visible, props.doc?.id] as const,
  async ([visible, id]) => {
    full.value = null
    if (!visible || id === undefined || id === null) return
    try {
      full.value = await fetchKbDoc(id)
    } catch {
      /* 保留基础数据 */
    }
  },
  { immediate: true },
)

const current = computed(() => full.value ?? props.doc)

const icon = computed(() => CATEGORY_ICON[current.value?.category ?? ''] ?? { cls: 'pdf', emoji: '📄' })
const badgeCls = computed(() => CATEGORY_BADGE[current.value?.category ?? ''] ?? 'sop')
const statusCls = computed(() => ({
  indexed: 'indexed',
  indexing: 'indexing',
  failed: 'failed',
}[current.value?.index_status ?? 'indexed']))
const statusLabel = computed(() => ({
  indexed: '已索引',
  indexing: '索引中',
  failed: '索引失败',
}[current.value?.index_status ?? 'indexed']))
const strategyLabel = computed(
  () => CHUNK_STRATEGY_LABELS[current.value?.strategy ?? 'paragraph'],
)

const doc = current // template 里用 doc 命名，避免大改

// 详情打开且该文档正在索引时，轮询刷新进度（与列表页的轮询节奏一致）
let pollTimer: ReturnType<typeof setInterval> | undefined
watch(
  () => [props.visible, full.value?.index_status] as const,
  ([visible, status]) => {
    clearInterval(pollTimer)
    if (visible && status === 'indexing') {
      pollTimer = setInterval(async () => {
        const id = props.doc?.id
        if (id === undefined || id === null) return
        try {
          full.value = await fetchKbDoc(id)
        } catch {
          /* 轮询失败忽略，下个周期重试 */
        }
      }, 1500)
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => clearInterval(pollTimer))

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
  width: 720px;
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
  gap: 14px;
  padding: 18px 22px;
  border-bottom: 1px solid var(--border);
}
.doc-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 23px;
  flex-shrink: 0;
}
.doc-icon.pdf { background: var(--red-bg); color: var(--red-text); }
.doc-icon.md { background: var(--amber-bg); color: var(--amber-text); }
.doc-icon.data { background: var(--green-bg); color: var(--green-text); }
.doc-icon.sop { background: var(--purple-bg); color: var(--purple-text); }

.header-info { flex: 1; min-width: 0; }
.doc-name {
  font-size: 16px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.header-badges { display: flex; gap: 6px; margin-top: 4px; align-items: center; }
.uploaded-by { font-size: 11px; color: var(--text-secondary); padding: 1px 4px; }

.header-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.header-actions .btn { padding: 8px 16px; font-size: 12.5px; }
.close {
  border: none;
  background: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text-secondary);
  line-height: 1;
}
.close:hover { color: var(--text); }

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
.badge.indexed { background: var(--green-bg); color: var(--green-text); }
.badge.indexing { background: var(--amber-bg); color: var(--amber-text); }
.badge.failed { background: var(--red-bg); color: var(--red-text); }

.body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.indexing-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--amber-border);
  background: var(--amber-bg);
  border-radius: 10px;
}
.progress {
  width: 220px;
  height: 6px;
  border-radius: 3px;
  background: #e7e5e4;
  overflow: hidden;
  flex-shrink: 0;
}
.progress i { display: block; height: 100%; background: var(--orange); border-radius: 3px; transition: width 0.4s ease; }
.progress-text { font-size: 12px; color: var(--amber-text); font-weight: 600; }

.sec-title { font-size: 13px; font-weight: 700; margin-bottom: 8px; }
.sec-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.sec-sub { font-size: 11px; color: var(--text-secondary); }

.desc { font-size: 13px; line-height: 1.7; color: var(--text); }
.tag-row { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.tag {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 2px 8px;
  border-radius: 6px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
@media (max-width: 700px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
.stat {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--bg);
}
.stat-label { font-size: 11px; color: var(--text-secondary); }
.stat-value { font-size: 20px; font-weight: 700; margin-top: 2px; }
.stat-value.green { color: var(--green-text); }

.failed-banner {
  padding: 10px 12px;
  border: 1px solid var(--red-border);
  background: var(--red-bg);
  border-radius: 10px;
  font-size: 12px;
  color: var(--red-text);
}

.info-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.info-table th {
  text-align: left;
  padding: 8px 12px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11.5px;
  font-weight: 600;
}
.info-table td { padding: 8px 12px; border: 1px solid var(--border); }
.info-table .mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--purple-text);
}
.info-table .muted { color: var(--text-secondary); }

.chunk-list { display: flex; flex-direction: column; gap: 6px; }
.chunk {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text);
}
.chunk-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--purple-text);
  font-size: 11px;
  margin-right: 8px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 22px;
  border-top: 1px solid var(--border);
}
.btn { padding: 10px 22px; font-size: 13px; }
.btn-ghost { background: #f5f5f4; color: var(--text); }
.btn-ghost:hover:not(:disabled) { background: #e7e5e4; }
.btn-ghost:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-danger-text { color: var(--red-text); }
.btn-danger-text:hover:not(:disabled) { background: var(--red-bg); }
</style>
