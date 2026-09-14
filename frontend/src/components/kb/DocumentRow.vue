<template>
  <div class="doc-row" :class="{ busy }">
    <div class="doc-icon" :class="icon.cls">{{ icon.emoji }}</div>

    <div class="doc-main">
      <div class="doc-name-line">
        <span class="doc-name">{{ doc.name }}</span>
        <span class="badge" :class="badgeCls">{{ doc.category }}</span>
        <span class="badge" :class="statusCls">{{ statusLabel }}</span>
      </div>

      <!-- 三种行内形态：索引中 → 进度条；失败 → 原因 + 重试；其余 → 标签 + 描述 -->
      <div v-if="doc.index_status === 'indexing'" class="indexing-wrap">
        <div class="progress"><i :style="{ width: (doc.index_progress ?? 1) + '%' }" /></div>
        <span class="progress-text">{{ doc.index_progress ?? 0 }}% · 剩余约 {{ doc.index_remaining_sec ?? '—' }} 秒</span>
      </div>
      <div v-else-if="doc.index_status === 'failed'" class="doc-desc failed">
        解析失败：{{ doc.index_error || '未知原因' }}。<button class="retry" @click="$emit('reindex', doc)">修复后重试 ↻</button>
      </div>
      <div v-else class="doc-desc">
        <span v-for="t in doc.tags" :key="t" class="tag">{{ t }}</span>{{ doc.description }}
      </div>
    </div>

    <div class="doc-meta">
      <span class="meta-chunks">
        {{ doc.chunk_count === null ? '—' : doc.chunk_count.toLocaleString('zh-CN') }} <span>块</span>
      </span>
      <span class="meta-date">{{ formatSize(doc.size_bytes) }} · {{ formatShortDate(doc.created_at) }}</span>
    </div>

    <div class="switch" :title="doc.index_status === 'failed' ? '索引失败，先重试索引' : '控制该文档是否参与检索'">
      <div class="switch-track" :class="{ on: doc.searchable }" @click="onToggle" />
      <span class="switch-label">参与检索</span>
    </div>

    <div class="card-actions">
      <button class="icon-btn" title="查看详情" @click="$emit('detail', doc)">👁</button>
      <button class="icon-btn" title="编辑" @click="$emit('edit', doc)">✎</button>
      <button class="icon-btn danger" title="删除" @click="$emit('remove', doc)">🗑</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  CATEGORY_BADGE, CATEGORY_ICON, formatShortDate, formatSize,
  type KbDoc,
} from '@/api/kb'

const props = defineProps<{ doc: KbDoc; busy?: boolean }>()
const emit = defineEmits<{
  (e: 'detail', doc: KbDoc): void
  (e: 'edit', doc: KbDoc): void
  (e: 'remove', doc: KbDoc): void
  (e: 'reindex', doc: KbDoc): void
  (e: 'toggle', doc: KbDoc): void
}>()

const icon = computed(() => CATEGORY_ICON[props.doc.category] ?? { cls: 'pdf', emoji: '📄' })
const badgeCls = computed(() => CATEGORY_BADGE[props.doc.category] ?? 'sop')

const statusCls = computed(() => ({
  indexed: 'indexed',
  indexing: 'indexing',
  failed: 'failed',
}[props.doc.index_status]))

const statusLabel = computed(() => ({
  indexed: '已索引',
  indexing: '索引中',
  failed: '索引失败',
}[props.doc.index_status]))

function onToggle() {
  if (props.doc.index_status === 'failed') return
  if (props.busy) return
  emit('toggle', props.doc)
}
</script>

<style scoped>
.doc-row {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 14px;
  transition: box-shadow 0.15s, border-color 0.15s, opacity 0.15s;
}
.doc-row:hover {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.07);
  border-color: var(--orange-border);
}
.doc-row.busy {
  opacity: 0.65;
  pointer-events: none;
}

.doc-icon {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 19px;
}
.doc-icon.pdf { background: var(--red-bg); color: var(--red-text); }
.doc-icon.md { background: var(--amber-bg); color: var(--amber-text); }
.doc-icon.data { background: var(--green-bg); color: var(--green-text); }
.doc-icon.sop { background: var(--purple-bg); color: var(--purple-text); }

.doc-main { flex: 1; min-width: 0; }
.doc-name-line { display: flex; align-items: center; gap: 8px; }
.doc-name {
  font-size: 13.5px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
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

.doc-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.doc-desc .tag {
  font-size: 11px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1px 7px;
  margin-right: 6px;
}
.doc-desc.failed { color: var(--red-text); }
.retry {
  border: none;
  background: none;
  color: var(--orange);
  font-weight: 600;
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
  padding: 0;
}
.retry:hover { text-decoration: underline; }

.indexing-wrap { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.progress {
  width: 160px;
  height: 5px;
  border-radius: 3px;
  background: #e7e5e4;
  overflow: hidden;
  flex-shrink: 0;
}
.progress i {
  display: block;
  height: 100%;
  background: var(--orange);
  border-radius: 3px;
  transition: width 0.4s ease;
}
.progress-text { font-size: 11px; color: var(--amber-text); font-weight: 600; }

.doc-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
  width: 120px;
}
.meta-chunks { font-size: 12px; color: var(--text); font-weight: 600; }
.meta-chunks span { color: var(--text-secondary); font-weight: 400; }
.meta-date { font-size: 11px; color: var(--text-secondary); }

.switch { flex-shrink: 0; display: flex; align-items: center; gap: 6px; }
.switch-track {
  width: 34px;
  height: 20px;
  border-radius: 10px;
  background: #d6d3d1;
  position: relative;
  cursor: pointer;
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
.switch-label { font-size: 11px; color: var(--text-secondary); }

.card-actions { display: flex; gap: 4px; flex-shrink: 0; }
.icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.icon-btn:hover { background: #f5f5f4; color: var(--text); }
.icon-btn.danger:hover { background: var(--red-bg); color: var(--red-text); }
</style>
