<template>
  <div v-if="visible" class="overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>{{ config.title }}</h3>
        <button class="close" @click="$emit('close')">×</button>
      </div>

      <div class="body">
        <p class="hint">{{ config.hint }}</p>

        <label v-for="field in config.fields" :key="field.key" class="field">
          <span class="label">{{ field.label }}</span>
          <input
            v-model="form[field.key]"
            :type="field.secret ? 'password' : 'text'"
            :placeholder="field.placeholder"
          />
        </label>
      </div>

      <div class="modal-footer">
        <button class="btn btn-ghost" @click="$emit('close')">取消</button>
        <button class="btn btn-primary" @click="save">保存</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

type Mode = 'knowledge' | 'settings'

const props = defineProps<{ visible: boolean; mode: Mode }>()
const emit = defineEmits<{ (e: 'close'): void }>()

interface FieldDef {
  key: string
  label: string
  placeholder: string
  secret?: boolean
}

interface ConfigDef {
  title: string
  hint: string
  fields: FieldDef[]
}

const DEFS: Record<Mode, ConfigDef> = {
  knowledge: {
    title: '知识库配置',
    hint: '配置 RAG 知识库接入，当前为占位（联调后生效）',
    fields: [
      { key: 'url', label: '知识库服务 URL', placeholder: 'https://...' },
      { key: 'apiKey', label: '知识库 API Key', placeholder: 'sk-...', secret: true },
    ],
  },
  settings: {
    title: '设置',
    hint: '配置默认 LLM 服务，当前为占位（联调后生效）',
    fields: [
      { key: 'url', label: 'LLM 服务 URL', placeholder: 'https://api.deepseek.com' },
      { key: 'apiKey', label: 'LLM API Key', placeholder: 'sk-...', secret: true },
      { key: 'model', label: '模型名称', placeholder: 'deepseek-chat' },
    ],
  },
}

const config = computed(() => DEFS[props.mode])

// mock：字段先空着，等待用户填写
const form = ref<Record<string, string>>({})

watch(
  () => props.visible,
  (v) => {
    if (v) {
      form.value = {}
      config.value.fields.forEach((f) => (form.value[f.key] = ''))
    }
  },
)

function save() {
  alert('（mock）配置已保存，联调后写入后端')
  emit('close')
}
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--surface);
  border-radius: 16px;
  width: 480px;
  max-width: 92vw;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.modal-header h3 {
  font-size: 16px;
}
.close {
  border: none;
  background: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text-secondary);
  line-height: 1;
}

.body {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field .label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}
.field input {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 14px;
  outline: none;
  background: #fafaf9;
}
.field input:focus {
  border-color: var(--orange);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}
.modal-footer .btn {
  padding: 10px 20px;
}
</style>
