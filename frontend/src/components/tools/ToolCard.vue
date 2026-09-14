<template>
  <div class="tool-card" :class="{ disabled: tool.status === 'disabled', deleted: tool.deleted }">
    <div class="card-top">
      <div class="tool-icon">{{ tool.icon || '🔧' }}</div>
      <div class="title-block">
        <div class="tool-name" :title="tool.display_name">{{ tool.display_name }}</div>
        <div class="badges">
          <span class="badge" :class="tool.source === 'mcp' ? 'mcp' : 'builtin'">
            {{ tool.source === 'mcp' ? 'MCP' : '内置' }}
          </span>
          <span v-if="tool.deleted" class="badge deleted-badge">已删除</span>
          <span v-else class="badge" :class="tool.status === 'enabled' ? 'enabled' : 'disabled-badge'">
            {{ tool.status === 'enabled' ? '已启用' : '已停用' }}
          </span>
        </div>
      </div>
      <div class="card-actions">
        <button class="icon-btn" title="查看详情" @click="$emit('detail', tool)">👁</button>
        <button class="icon-btn" title="编辑" @click="$emit('edit', tool)">✎</button>
        <!-- ⚠️ 仅当后端 capabilities.can_delete 为真才渲染删除按钮。
             内置工具（bash/gaussian 等）删了 Agent 会瘫痪，后端会返回 409，
             前端据此隐藏入口，而不是让用户点了才吃报错。 -->
        <button
          v-if="tool.capabilities.can_delete"
          class="icon-btn danger"
          title="删除"
          @click="$emit('remove', tool)"
        >🗑</button>
        <button
          v-else-if="tool.deleted && tool.capabilities.can_restore"
          class="icon-btn"
          title="恢复"
          @click="$emit('restore', tool)"
        >↺</button>
        <span
          v-else-if="!tool.deleted && tool.capabilities.delete_blocked_reason"
          class="icon-btn locked"
          :title="tool.capabilities.delete_blocked_reason"
        >🔒</span>
      </div>
    </div>

    <div class="tool-desc">{{ tool.user_description || '（暂无介绍）' }}</div>

    <div v-if="tool.tags.length" class="tag-row">
      <span v-for="t in tool.tags.slice(0, 4)" :key="t" class="tag">{{ t }}</span>
      <span v-if="tool.tags.length > 4" class="tag more">+{{ tool.tags.length - 4 }}</span>
    </div>

    <div class="card-footer">
      <span>调用 {{ formatCount(tool.invocation_count) }} 次</span>
      <span class="dot">·</span>
      <span>更新于 {{ formatTime(tool.updated_at) }}</span>
      <button
        v-if="!tool.deleted"
        class="switch"
        :class="{ on: tool.status === 'enabled', busy }"
        :title="tool.status === 'enabled' ? '点击停用' : '点击启用'"
        :disabled="busy"
        @click="$emit('toggle', tool)"
      >
        <span class="track" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatCount, formatTime, type Tool } from '@/api/tools'

defineProps<{ tool: Tool; busy?: boolean }>()
defineEmits<{
  (e: 'detail', tool: Tool): void
  (e: 'edit', tool: Tool): void
  (e: 'remove', tool: Tool): void
  (e: 'restore', tool: Tool): void
  (e: 'toggle', tool: Tool): void
}>()
</script>

<style scoped>
.tool-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.tool-card:hover {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.07);
  border-color: var(--orange-border);
}
.tool-card.disabled {
  opacity: 0.78;
}
.tool-card.deleted {
  opacity: 0.6;
  border-style: dashed;
}

.card-top {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.tool-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  flex-shrink: 0;
  background: var(--orange-light);
  color: var(--orange);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.title-block {
  flex: 1;
  min-width: 0;
}
.tool-name {
  font-size: 14px;
  font-weight: 700;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.badges {
  display: flex;
  gap: 6px;
  margin-top: 5px;
  flex-wrap: wrap;
}
.badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
  white-space: nowrap;
}
.badge.builtin {
  background: var(--amber-bg);
  color: var(--amber-text);
}
.badge.mcp {
  background: var(--purple-bg);
  color: var(--purple-text);
}
.badge.enabled {
  background: var(--green-bg);
  color: var(--green-text);
}
.badge.disabled-badge,
.badge.deleted-badge {
  background: #f5f5f4;
  color: var(--text-secondary);
}

.card-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}
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
  transition: background 0.12s, color 0.12s;
}
.icon-btn:hover {
  background: #f5f5f4;
  color: var(--text);
}
.icon-btn.danger:hover {
  background: var(--red-bg);
  color: var(--red-text);
}
.icon-btn.locked {
  cursor: help;
  opacity: 0.5;
}
.icon-btn.locked:hover {
  background: none;
  color: var(--text-secondary);
}

.tool-desc {
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 9px 0 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 37px;
}

.tag-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.tag {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 2px 8px;
  border-radius: 6px;
}
.tag.more {
  color: var(--text-secondary);
}

.card-footer {
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text-secondary);
}
.dot {
  opacity: 0.5;
}

.switch {
  margin-left: auto;
  width: 34px;
  height: 20px;
  border-radius: 10px;
  background: #d6d3d1;
  border: none;
  cursor: pointer;
  position: relative;
  padding: 0;
  transition: background 0.15s;
  flex-shrink: 0;
}
.switch.on {
  background: var(--orange);
}
.switch:disabled {
  opacity: 0.5;
  cursor: wait;
}
.switch .track {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: left 0.15s;
}
.switch.on .track {
  left: 16px;
}
</style>
