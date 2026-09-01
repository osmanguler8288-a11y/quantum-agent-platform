<template>
  <div v-if="visible" class="overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>分子结构输入</h3>
        <button class="close" @click="$emit('close')">×</button>
      </div>

      <div class="tabs">
        <button :class="{ active: mode === 'xyz' }" @click="mode = 'xyz'">XYZ 坐标</button>
        <button :class="{ active: mode === 'smiles' }" @click="mode = 'smiles'">SMILES</button>
        <button :class="{ active: mode === 'file' }" @click="mode = 'file'">上传文件</button>
      </div>

      <div class="body">
        <template v-if="mode === 'xyz'">
          <textarea v-model="xyz" rows="8" placeholder="6&#10;benzene&#10;C 0.0 1.394 0.0&#10;..."></textarea>
        </template>

        <template v-else-if="mode === 'smiles'">
          <input v-model="smiles" type="text" placeholder="如 c1ccccc1（苯）" />
          <p class="hint">SMILES 会由后端用 RDKit 生成 3D 结构</p>
        </template>

        <template v-else>
          <input type="file" accept=".xyz,.mol,.sdf" @change="onFile" />
          <p v-if="fileName" class="hint">已选择: {{ fileName }}</p>
        </template>
      </div>

      <div class="modal-footer">
        <button class="btn btn-ghost" @click="$emit('close')">取消</button>
        <button class="btn btn-primary" :disabled="!valid" @click="confirm">确认</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'confirm', structure: { format: string; data: string; filename?: string }): void
}>()

const mode = ref<'xyz' | 'smiles' | 'file'>('xyz')
const xyz = ref('')
const smiles = ref('')
const fileName = ref('')
const fileData = ref('')

const valid = computed(() => {
  if (mode.value === 'xyz') return xyz.value.trim().length > 0
  if (mode.value === 'smiles') return smiles.value.trim().length > 0
  return fileData.value.length > 0
})

function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  fileName.value = file.name
  const reader = new FileReader()
  reader.onload = () => {
    fileData.value = String(reader.result || '')
  }
  reader.readAsText(file)
}

function confirm() {
  if (mode.value === 'xyz') {
    emit('confirm', { format: 'xyz', data: xyz.value.trim() })
  } else if (mode.value === 'smiles') {
    emit('confirm', { format: 'smiles', data: smiles.value.trim() })
  } else {
    emit('confirm', { format: 'file', data: fileData.value, filename: fileName.value })
  }
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
  width: 520px;
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

.tabs {
  display: flex;
  gap: 4px;
  padding: 12px 20px 0;
}
.tabs button {
  border: 1px solid var(--border);
  background: #fafaf9;
  border-radius: 8px 8px 0 0;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
}
.tabs button.active {
  background: var(--surface);
  color: var(--orange);
  border-bottom-color: var(--surface);
  font-weight: 600;
}

.body {
  padding: 16px 20px;
}

textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 13px;
  outline: none;
  resize: vertical;
}
textarea:focus {
  border-color: var(--orange);
}

.body input[type='text'] {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 14px;
  outline: none;
}
.body input[type='text']:focus {
  border-color: var(--orange);
}

.hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 8px;
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
