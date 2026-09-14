<template>
  <div v-if="visible" class="overlay" @click.self="$emit('cancel')">
    <div class="dialog">
      <div class="head">
        <div class="icon">⚠</div>
        <div class="txt">
          <div class="title">{{ title }}</div>
          <div class="message">
            <slot name="message">{{ message }}</slot>
          </div>
        </div>
      </div>

      <div v-if="warning" class="warning" :class="warningTone">{{ warning }}</div>

      <div class="footer">
        <button class="btn btn-ghost" @click="$emit('cancel')">取消</button>
        <button class="btn btn-danger" :disabled="busy" @click="$emit('confirm')">
          {{ busy ? '处理中…' : confirmText }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  visible: boolean
  title: string
  message: string
  /** 风险提示（如「近 30 天被检索引用 N 次」），默认红底展示 */
  warning?: string
  /** 风险提示配色：red 用于删除类风险，amber 用于一般性提醒（如整库重建） */
  warningTone?: 'red' | 'amber'
  confirmText?: string
  busy?: boolean
}>(), { confirmText: '确认删除', warning: '', warningTone: 'red', busy: false })

defineEmits<{ (e: 'cancel'): void; (e: 'confirm'): void }>()
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(28, 25, 23, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 20px;
}
.dialog {
  width: 440px;
  max-width: 100%;
  background: var(--surface);
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}

.head {
  padding: 22px 24px 0;
  display: flex;
  gap: 14px;
}
.icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: var(--red-bg);
  color: var(--red-text);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.txt { flex: 1; min-width: 0; }
.title {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.4;
}
.message {
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-top: 6px;
}
.message :deep(b) {
  color: var(--text);
  font-weight: 600;
}

.warning {
  margin: 16px 24px 0;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.5;
}
.warning.red {
  border: 1px solid var(--red-border);
  background: var(--red-bg);
  color: var(--red-text);
}
.warning.amber {
  border: 1px solid var(--amber-border);
  background: var(--amber-bg);
  color: var(--amber-text);
}
.warning :deep(b) { font-weight: 700; }

.footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 18px 24px 20px;
}
.btn {
  padding: 10px 20px;
  font-size: 13px;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  font-weight: 600;
  font-family: inherit;
}
.btn-ghost {
  background: #f5f5f4;
  color: var(--text);
}
.btn-ghost:hover { background: #e7e5e4; }
.btn-danger {
  background: var(--red-text);
  color: #fff;
}
.btn-danger:hover { background: #7f1d1d; }
.btn-danger:disabled { opacity: 0.6; cursor: wait; }
</style>
