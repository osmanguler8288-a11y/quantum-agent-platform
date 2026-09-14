<template>
  <div v-if="visible" class="overlay" @click.self="close">
    <div class="modal">
      <div class="modal-header">
        <div class="modal-icon">＋</div>
        <div class="header-text">
          <div class="modal-title">新建对话</div>
          <div class="header-sub">仅设置必要的初始项，其余参数可在对话中随时调整</div>
        </div>
        <button class="close" @click="close">×</button>
      </div>

      <div class="modal-body">
        <div class="field">
          <span class="label">选择模型 <b>*</b></span>
          <div class="model-select">
            <button
              v-for="m in MODEL_OPTIONS"
              :key="m.id"
              type="button"
              class="model-option"
              :class="{ active: form.model === m.id }"
              @click="form.model = m.id"
            >
              <span class="m-mark">{{ m.mark }}</span>
              <span class="m-name">{{ m.name }}</span>
              <span class="m-meta">{{ m.meta }}</span>
            </button>
          </div>
        </div>

        <label class="field">
          <span class="label">对话标题 <span class="hint">（可选，留空则取首条消息前 20 字）</span></span>
          <input v-model="form.title" type="text" placeholder="给对话起个名字，如「偶氮苯光开关构型筛选」" />
        </label>

        <label class="field">
          <span class="label">系统提示 <span class="hint">（可选）</span></span>
          <textarea
            v-model="form.systemPrompt"
            rows="3"
            placeholder="设定 Agent 的角色与回答风格，如「你是一名计算化学专家助手…」"
          />
        </label>
      </div>

      <div v-if="error" class="error-bar">{{ error }}</div>

      <div class="modal-footer">
        <button class="btn btn-ghost" @click="close">取消</button>
        <button class="btn btn-primary" :disabled="creating" @click="submit">
          {{ creating ? '创建中…' : '＋ 创建并打开' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { MODEL_OPTIONS, createConversation, type ConvDetail } from '@/api/conversation'
import { isApiNotFound } from '@/api/client'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', conv: ConvDetail): void
  /** 后端暂无 /api/conversations 路由（404）→ 降级为本地新建，直接进新对话界面 */
  (e: 'create-local'): void
}>()

const form = reactive({
  model: MODEL_OPTIONS[0].id as string,
  title: '',
  systemPrompt: '',
})
const creating = ref(false)
const error = ref('')

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    form.model = MODEL_OPTIONS[0].id
    form.title = ''
    form.systemPrompt = ''
    error.value = ''
    creating.value = false
  },
)

async function submit() {
  error.value = ''
  creating.value = true
  try {
    const conv = await createConversation({
      model: form.model,
      title: form.title.trim() || undefined,
      system_prompt: form.systemPrompt.trim() || undefined,
    })
    emit('created', conv)
    close()
  } catch (e) {
    // 后端路由未就绪 → 不报错，直接以本地新对话进入聊天页
    if (isApiNotFound(e)) {
      emit('create-local')
      close()
      return
    }
    error.value = (e as Error).message
  } finally {
    creating.value = false
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
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--border);
}
.modal-icon {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: var(--orange-light);
  color: var(--orange);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  flex-shrink: 0;
}
.header-text { flex: 1; min-width: 0; }
.modal-title { font-size: 16px; font-weight: 700; }
.header-sub { font-size: 11.5px; color: var(--text-secondary); margin-top: 2px; }
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

input,
textarea {
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
input:focus,
textarea:focus { border-color: var(--orange); }
textarea { resize: vertical; line-height: 1.5; min-height: 72px; }

.model-select {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.model-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  cursor: pointer;
  font-size: 13px;
  border: none;
  background: none;
  font-family: inherit;
  color: var(--text);
  text-align: left;
}
.model-option + .model-option { border-top: 1px solid var(--border); }
.model-option:hover { background: var(--bg); }
.model-option.active { background: var(--orange-light); }
.m-mark {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  background: var(--purple-bg);
  color: var(--purple-text);
}
.model-option.active .m-mark { background: var(--orange); color: #fff; }
.m-name { font-weight: 700; flex: 1; }
.model-option.active .m-name { color: var(--orange-hover); }
.m-meta { font-size: 11px; color: var(--text-secondary); }

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
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 22px 18px;
  border-top: 1px solid var(--border);
  background: var(--bg);
  margin-top: 6px;
}
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
