<template>
  <div class="conv-row" :class="{ archived: conv.status === 'archived' }" @click="$emit('open', conv)">
    <div class="conv-avatar" :class="avatarCls" :style="{ opacity: conv.status === 'archived' ? 0.55 : undefined }">
      {{ avatarChar }}
    </div>

    <div class="conv-main" :style="conv.status === 'archived' ? 'opacity:.7' : undefined">
      <div class="title-line">
        <span v-if="conv.pinned" class="pin" title="已置顶">📌</span>
        <span class="conv-name" :class="{ struck: conv.status === 'archived' }">{{ conv.title }}</span>
        <span class="badge" :class="statusCls">{{ statusLabel }}</span>
        <span class="badge model">{{ modelLabel(conv.model) }}</span>
      </div>
      <div class="preview-line">
        <span class="snippet">{{ conv.snippet }}</span>
        <span v-for="t in conv.tags" :key="t" class="tag">{{ t }}</span>
      </div>
    </div>

    <div class="conv-side">
      <span class="time">{{ formatRelativeTime(conv.updated_at) }}</span>
      <span class="cnt">{{ conv.message_count }} 条消息</span>
    </div>

    <div class="card-actions">
      <button class="icon-btn" title="查看详情" @click.stop="$emit('detail', conv)">👁</button>
      <button class="icon-btn" title="编辑" @click.stop="$emit('edit', conv)">✎</button>
      <button class="icon-btn danger" title="删除" @click.stop="$emit('remove', conv)">🗑</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatRelativeTime, modelLabel, type ConvSummary } from '@/api/conversation'

const props = defineProps<{ conv: ConvSummary }>()

defineEmits<{
  (e: 'open', conv: ConvSummary): void
  (e: 'detail', conv: ConvSummary): void
  (e: 'edit', conv: ConvSummary): void
  (e: 'remove', conv: ConvSummary): void
}>()

const avatarCls = computed(() => ({
  active: 'live',
  completed: 'done',
  archived: 'chat',
}[props.conv.status]))

const avatarChar = computed(() => ({
  active: '⚡',
  completed: '✓',
  archived: '💬',
}[props.conv.status]))

const statusCls = computed(() => ({
  active: 'live',
  completed: 'done',
  archived: 'archive',
}[props.conv.status]))

const statusLabel = computed(() => ({
  active: '进行中',
  completed: '已完成',
  archived: '已归档',
}[props.conv.status]))
</script>

<style scoped>
.conv-row {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  gap: 14px;
  transition: box-shadow 0.15s, border-color 0.15s;
  cursor: pointer;
}
.conv-row:hover {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.07);
  border-color: var(--orange-border);
}

.conv-avatar {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
}
.conv-avatar.chat { background: #f5f5f4; color: var(--text-secondary); }
.conv-avatar.live {
  background: var(--orange-light);
  color: var(--orange);
  animation: pulse 1.6s ease-in-out infinite;
}
.conv-avatar.done { background: var(--green-bg); color: var(--green-text); }

@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(217, 119, 6, 0.35); }
  50% { box-shadow: 0 0 0 6px rgba(217, 119, 6, 0); }
}

.conv-main { flex: 1; min-width: 0; }
.title-line { display: flex; align-items: center; gap: 8px; }
.pin { font-size: 12px; color: var(--orange); line-height: 1; }
.conv-name {
  font-size: 13.5px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 460px;
}
.conv-name.struck {
  text-decoration: line-through;
  color: var(--text-secondary);
}
.badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
  flex-shrink: 0;
}
.badge.live { background: var(--orange-light); color: var(--orange-hover); }
.badge.done { background: var(--green-bg); color: var(--green-text); }
.badge.archive { background: #f5f5f4; color: var(--text-secondary); }
.badge.model { background: var(--purple-bg); color: var(--purple-text); }

.preview-line {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.snippet {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 560px;
}
.tag {
  font-size: 11px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1px 7px;
  flex-shrink: 0;
}

.conv-side {
  flex-shrink: 0;
  width: 150px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-end;
}
.conv-side .time { font-size: 12.5px; font-weight: 600; }
.conv-side .cnt { font-size: 11.5px; color: var(--text-secondary); }

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
