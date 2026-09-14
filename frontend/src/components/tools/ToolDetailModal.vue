<template>
  <div v-if="visible" class="overlay" @click.self="$emit('close')">
    <div class="modal">
      <template v-if="tool">
        <!-- 头部 -->
        <div class="head">
          <div class="tool-icon">{{ tool.icon || '🔧' }}</div>
          <div class="head-main">
            <div class="name-row">
              <span class="tool-name">{{ tool.display_name }}</span>
              <span class="badge" :class="tool.source === 'mcp' ? 'mcp' : 'builtin'">
                {{ tool.source === 'mcp' ? 'MCP' : '内置' }}
              </span>
              <span class="badge" :class="tool.status === 'enabled' ? 'enabled' : 'muted-badge'">
                {{ tool.status === 'enabled' ? '已启用' : '已停用' }}
              </span>
            </div>
            <div class="meta">
              {{ tool.category }} · 创建于 {{ formatDate(tool.created_at) }}
              <span class="mono-id">{{ tool.name }}</span>
            </div>
          </div>
          <div class="head-actions">
            <button class="btn btn-ghost sm" @click="$emit('edit', tool)">编辑</button>
            <button class="close" @click="$emit('close')">×</button>
          </div>
        </div>

        <div class="body">
          <!-- 介绍 -->
          <section>
            <h4>工具介绍</h4>
            <p class="desc">{{ tool.user_description || '（暂无介绍）' }}</p>
          </section>

          <!-- 统计四宫格 -->
          <section v-if="tool.stats">
            <h4>调用统计</h4>
            <div class="stats">
              <div class="stat">
                <div class="val">{{ formatCount(tool.stats.total_invocations) }}</div>
                <div class="key">累计调用</div>
              </div>
              <div class="stat">
                <!-- ⚠️ 无调用记录时后端返回 null，展示「—」而不是 NaN 或 0% -->
                <div class="val">{{ formatRate(tool.stats.success_rate) }}</div>
                <div class="key">成功率</div>
              </div>
              <div class="stat">
                <div class="val">{{ formatDuration(tool.stats.avg_duration_ms) }}</div>
                <div class="key">平均耗时</div>
              </div>
              <div class="stat">
                <div class="val">{{ formatTime(tool.stats.last_invoked_at) }}</div>
                <div class="key">最近调用</div>
              </div>
            </div>
          </section>

          <!-- 参数说明表 -->
          <section>
            <h4>参数说明</h4>
            <table v-if="tool.param_rows?.length" class="params">
              <thead>
                <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
              </thead>
              <tbody>
                <tr v-for="p in tool.param_rows" :key="p.name">
                  <td class="mono-id">{{ p.name }}</td>
                  <td>{{ p.type }}</td>
                  <td>{{ p.required ? '是' : '否' }}</td>
                  <td class="param-desc">{{ p.description || '—' }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="empty-line">该工具无需参数</p>
          </section>

          <!-- 最近调用记录 -->
          <section>
            <h4>最近调用记录</h4>
            <div v-if="tool.recent_invocations?.length" class="inv-list">
              <div v-for="inv in tool.recent_invocations" :key="inv.id" class="inv-row">
                <span class="mono-id">#{{ inv.id }}</span>
                <span class="inv-title">{{ inv.task_title || '（无标题）' }}</span>
                <span class="inv-status" :class="inv.status">
                  {{ inv.status === 'success' ? '成功' : '失败' }}
                </span>
                <span class="inv-dur">{{ formatDuration(inv.duration_ms) }}</span>
                <span class="inv-time">{{ formatTime(inv.started_at) }}</span>
              </div>
            </div>
            <p v-else class="empty-line">暂无调用记录</p>
          </section>
        </div>

        <div class="modal-footer">
          <button
            v-if="tool.capabilities.can_delete"
            class="btn btn-danger"
            @click="$emit('remove', tool)"
          >删除工具</button>
          <span v-else-if="tool.capabilities.delete_blocked_reason" class="locked-hint">
            🔒 {{ tool.capabilities.delete_blocked_reason }}
          </span>
          <button class="btn btn-ghost" @click="$emit('close')">关闭</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  formatCount, formatDate, formatDuration, formatRate, formatTime, type Tool,
} from '@/api/tools'

defineProps<{ visible: boolean; tool: Tool | null }>()
defineEmits<{
  (e: 'close'): void
  (e: 'edit', tool: Tool): void
  (e: 'remove', tool: Tool): void
}>()
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

.head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 20px 20px 14px;
  border-bottom: 1px solid var(--border);
}
.tool-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: var(--orange-light);
  color: var(--orange);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
}
.head-main {
  flex: 1;
  min-width: 0;
}
.name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tool-name {
  font-size: 17px;
  font-weight: 700;
}
.badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.badge.builtin { background: var(--amber-bg); color: var(--amber-text); }
.badge.mcp { background: var(--purple-bg); color: var(--purple-text); }
.badge.enabled { background: var(--green-bg); color: var(--green-text); }
.badge.muted-badge { background: #f5f5f4; color: var(--text-secondary); }

.meta {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.mono-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11.5px;
  color: var(--text-secondary);
  background: var(--bg);
  padding: 1px 6px;
  border-radius: 5px;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.close {
  border: none;
  background: none;
  font-size: 22px;
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0 4px;
  border-radius: 6px;
}
.close:hover { background: #f5f5f4; color: var(--text); }

.body {
  padding: 16px 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
section h4 {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 9px;
}
.desc {
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.stat {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 10px;
  text-align: center;
}
.stat .val {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}
.stat .key {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.params {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.params th {
  text-align: left;
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 11.5px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}
.params td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.param-desc {
  color: var(--text-secondary);
}

.inv-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.inv-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg);
}
.inv-title {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.inv-status {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 10px;
}
.inv-status.success { background: var(--green-bg); color: var(--green-text); }
.inv-status.error { background: var(--red-bg); color: var(--red-text); }
.inv-dur,
.inv-time {
  color: var(--text-secondary);
  font-size: 11.5px;
  white-space: nowrap;
}

.empty-line {
  font-size: 12.5px;
  color: var(--text-secondary);
  padding: 10px;
  background: var(--bg);
  border-radius: 8px;
}

.modal-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px 18px;
  border-top: 1px solid var(--border);
}
.btn {
  padding: 9px 18px;
  font-size: 13px;
}
.btn.sm {
  padding: 6px 14px;
  font-size: 12.5px;
}
.btn-ghost {
  background: #f5f5f4;
  color: var(--text);
  margin-left: auto;
}
.btn-ghost:hover { background: #e7e5e4; }
.btn-danger {
  background: var(--red-bg);
  color: var(--red-text);
  border: 1px solid var(--red-border);
}
.btn-danger:hover { background: #fee2e2; }
.locked-hint {
  font-size: 12px;
  color: var(--text-secondary);
  flex: 1;
}
</style>
