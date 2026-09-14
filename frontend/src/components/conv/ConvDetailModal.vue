<template>
  <div v-if="visible && convId !== null" class="overlay" @click.self="$emit('close')">
    <div class="modal">
      <template v-if="detail">
        <!-- 头部 -->
        <div class="modal-header">
          <div class="header-avatar" :class="detail.status">{{ avatarChar }}</div>
          <div class="header-text">
            <div class="header-title-line">
              <span v-if="detail.pinned" class="pin">📌</span>
              <span class="header-title">{{ detail.title }}</span>
              <span class="badge" :class="statusCls">{{ statusLabel }}</span>
              <span class="badge model">{{ modelLabel(detail.model) }}</span>
            </div>
            <div class="header-meta">
              <span>📅 创建于 <b>{{ formatRelativeTime(detail.created_at) }}</b></span>
              <i class="dot">·</i>
              <span>最近活动 <b>{{ formatRelativeTime(detail.updated_at) }}</b></span>
              <i class="dot">·</i>
              <span v-if="detail.tags.length">🏷 <b>{{ detail.tags.join(' / ') }}</b></span>
            </div>
          </div>
          <div class="header-actions">
            <button class="icon-btn" title="编辑" @click="$emit('edit', detail)">✎</button>
            <button class="icon-btn danger" title="删除" @click="$emit('remove', detail)">🗑</button>
          </div>
        </div>

        <!-- 系统提示 -->
        <div v-if="detail.system_prompt" class="sys-tip">
          <b>系统提示：</b>{{ detail.system_prompt }}
        </div>

        <!-- 主体 -->
        <div class="modal-body">
          <div>
            <div class="section-title">
              消息预览 <span class="num">（共 {{ detail.message_count }} 条，进入对话查看全部）</span>
            </div>

            <details class="collapse-block" open>
              <summary>用户首条消息</summary>
              <div class="body">
                <div class="msg">
                  <span class="role u">USER</span>{{ detail.first_message?.content ?? '（暂无消息）' }}
                </div>
              </div>
            </details>

            <details class="collapse-block">
              <summary>Agent 最近一次回复</summary>
              <div class="body">
                <div class="msg">
                  <span class="role a">AGENT</span>{{ detail.last_reply?.content ?? '（暂无回复）' }}
                </div>
              </div>
            </details>
          </div>

          <div>
            <div class="section-title">统计</div>
            <div class="stat-grid">
              <div class="stat-cell">
                <div class="label">消息数</div>
                <div class="v">{{ detail.message_count }}</div>
              </div>
              <div class="stat-cell">
                <div class="label">工具调用</div>
                <div class="v">{{ detail.tool_calls }} <span class="u">次</span></div>
              </div>
              <div class="stat-cell">
                <div class="label">总 Tokens</div>
                <div class="v">{{ detail.total_tokens.toLocaleString('zh-CN') }}</div>
              </div>
              <div class="stat-cell">
                <div class="label">累计费用</div>
                <div class="v">{{ formatCost(detail.total_cost) }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部 -->
        <div class="modal-footer">
          <button class="btn-left" @click="$emit('remove', detail)">🗑 删除对话</button>
          <div class="btn-right">
            <button class="btn btn-primary" @click="$emit('continue', detail)">继续对话 →</button>
          </div>
        </div>
      </template>

      <div v-else-if="loading" class="state-block">加载中…</div>
      <div v-else class="state-block error">
        <p>{{ error || '对话不存在或已被删除' }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  fetchConversation, formatCost, formatRelativeTime, modelLabel,
  type ConvDetail,
} from '@/api/conversation'
import { isApiNotFound } from '@/api/client'

const props = defineProps<{ visible: boolean; convId: number | null }>()
defineEmits<{
  (e: 'close'): void
  (e: 'edit', conv: ConvDetail): void
  (e: 'remove', conv: ConvDetail): void
  (e: 'continue', conv: ConvDetail): void
}>()

const detail = ref<ConvDetail | null>(null)
const loading = ref(false)
const error = ref('')

watch(
  () => [props.visible, props.convId] as const,
  ([visible, id]) => {
    if (!visible || id === null) {
      detail.value = null
      return
    }
    error.value = ''
    detail.value = null
    loading.value = true
    fetchConversation(id)
      .then((d) => (detail.value = d))
      .catch((e) => {
        error.value = isApiNotFound(e) ? '' : `加载失败：${(e as Error).message}`
      })
      .finally(() => (loading.value = false))
  },
  { immediate: true },
)

const avatarChar = computed(() => ({
  active: '⚡',
  completed: '✓',
  archived: '💬',
}[detail.value?.status ?? 'completed']))

const statusCls = computed(() => ({
  active: 'live',
  completed: 'done',
  archived: 'archive',
}[detail.value?.status ?? 'completed']))

const statusLabel = computed(() => ({
  active: '进行中',
  completed: '已完成',
  archived: '已归档',
}[detail.value?.status ?? 'completed']))
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
  max-height: 860px;
  background: var(--surface);
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  padding: 16px 22px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.header-avatar {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 700;
}
.header-avatar.active { background: var(--orange-light); color: var(--orange); }
.header-avatar.completed { background: var(--green-bg); color: var(--green-text); }
.header-avatar.archived { background: #f5f5f4; color: var(--text-secondary); }
.header-text { flex: 1; min-width: 0; }
.header-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.header-title {
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
  max-width: 380px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pin { color: var(--orange); font-size: 13px; }
.badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.badge.live { background: var(--orange-light); color: var(--orange-hover); }
.badge.done { background: var(--green-bg); color: var(--green-text); }
.badge.archive { background: #f5f5f4; color: var(--text-secondary); }
.badge.model { background: var(--purple-bg); color: var(--purple-text); }
.header-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11.5px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}
.header-meta .dot { color: #d6d3d1; font-style: normal; }
.header-meta b { color: var(--text); }
.header-actions { display: flex; gap: 6px; flex-shrink: 0; }
.icon-btn {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
}
.icon-btn:hover { background: #f5f5f4; color: var(--text); }
.icon-btn.danger:hover { background: var(--red-bg); color: var(--red-text); }

.sys-tip {
  margin: 12px 22px 0;
  background: var(--amber-bg);
  border-left: 3px solid var(--orange);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 11.5px;
  color: var(--amber-text);
}
.sys-tip b { color: var(--text); font-weight: 700; }

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 22px 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.section-title {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 600;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.section-title .num { color: var(--orange); font-weight: 400; }

.collapse-block {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}
.collapse-block summary {
  padding: 10px 14px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
}
.collapse-block summary::-webkit-details-marker { display: none; }
.collapse-block summary::before {
  content: '▸';
  font-size: 10px;
  color: var(--text-secondary);
}
.collapse-block[open] summary::before { content: '▾'; }
.collapse-block[open] summary { border-bottom: 1px solid var(--border); }
.collapse-block .body { padding: 10px 14px; }
.collapse-block .body .msg {
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}
.collapse-block .body .role {
  font-size: 10.5px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 5px;
  margin-right: 6px;
}
.collapse-block .body .role.u { background: var(--orange-light); color: var(--orange-hover); }
.collapse-block .body .role.a { background: #f0f9ff; color: #075985; }
.collapse-block + .collapse-block { margin-top: 8px; }

.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.stat-cell {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
}
.stat-cell .label { font-size: 10.5px; color: var(--text-secondary); }
.stat-cell .v {
  font-size: 16px;
  font-weight: 700;
  margin-top: 3px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.stat-cell .v .u {
  font-size: 11px;
  color: var(--text-secondary);
  margin-left: 1px;
  font-weight: 400;
}

.modal-footer {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 22px 14px;
  border-top: 1px solid var(--border);
  background: var(--bg);
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
  padding: 10px 18px;
  font-size: 13px;
}
.btn-primary { background: var(--orange); color: #fff; }
.btn-primary:hover { background: var(--orange-hover); }

.state-block {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
.state-block.error { color: var(--red-text); }
</style>
