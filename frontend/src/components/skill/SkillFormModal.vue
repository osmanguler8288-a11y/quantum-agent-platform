<template>
  <div v-if="visible" class="overlay" @click.self="close">
    <div class="modal">
      <div class="modal-head">
        <div class="modal-title">
          {{ isEdit ? '编辑技能' : '新建技能' }}
          <div class="modal-sub">按顺序编排工具步骤，前一步的输出会作为后一步的输入</div>
        </div>
        <button class="close" @click="close">✕</button>
      </div>

      <div class="modal-body">
        <div class="field">
          <div class="field-label">技能名称 <span class="req">*</span></div>
          <input
            v-model="form.name"
            class="input"
            type="text"
            placeholder="如：TADF 候选分子批量筛选"
          />
        </div>

        <div class="field">
          <div class="field-label">
            描述 <span class="opt">（可选，帮助子代理判断何时使用该技能）</span>
          </div>
          <textarea
            v-model="form.description"
            class="textarea"
            placeholder="一句话说明这个技能做什么、适合什么任务"
          />
        </div>

        <div class="field" style="margin-bottom: 0">
          <div class="steps-head">
            <div class="field-label">工作流步骤 <span class="req">*</span></div>
            <span class="count">{{ form.steps.length }} 步</span>
          </div>

          <div class="step-list">
            <div v-for="(step, i) in form.steps" :key="i" class="step-row">
              <div class="step-no">{{ i + 1 }}</div>
              <div class="step-fields">
                <select v-model.number="step.tool_id" class="select">
                  <option :value="0" disabled>选择工具…</option>
                  <option v-for="t in tools" :key="t.id" :value="t.id">
                    {{ t.icon }} {{ t.display_name }}
                  </option>
                </select>
                <input
                  v-model="step.note"
                  class="input"
                  type="text"
                  placeholder="给这一步的说明（可选），如：保留收敛且能量最低的构象"
                />
              </div>
              <div class="step-ops">
                <button
                  class="icon-btn"
                  :disabled="i === 0"
                  title="上移"
                  @click="move(i, -1)"
                >↑</button>
                <button
                  class="icon-btn"
                  :disabled="i === form.steps.length - 1"
                  title="下移"
                  @click="move(i, 1)"
                >↓</button>
                <button class="icon-btn danger" title="移除" @click="form.steps.splice(i, 1)">🗑</button>
              </div>
            </div>

            <button class="add-step" type="button" @click="addStep">＋ 添加步骤</button>
          </div>

          <div v-if="!tools.length" class="field-hint warn">
            工具库暂不可用或没有启用中的工具，无法选择步骤——请先到「工具库」启用至少一个工具。
          </div>

          <div class="use-tip">
            💡 保存后，在对话中说「用 <b>{{ form.name.trim() || '这个技能' }}</b> 处理这批分子」即可调用这个子代理。
          </div>
        </div>
      </div>

      <div v-if="error" class="error-bar">{{ error }}</div>

      <div class="modal-foot">
        <button class="btn btn-ghost" @click="close">取消</button>
        <button class="btn btn-save" :disabled="saving" @click="submit">
          {{ saving ? '保存中…' : isEdit ? '保存修改' : '创建技能' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { createSkill, updateSkill, type Skill } from '@/api/skill'
import type { Tool } from '@/api/tools'

const props = defineProps<{
  visible: boolean
  /** 编辑时传入技能，新建时传 null */
  skill: Skill | null
  /** 可选工具（启用中的），来自工具库列表接口 */
  tools: Tool[]
}>()

const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()

interface StepDraft {
  tool_id: number // 0 = 未选择
  note: string
}

const form = reactive({
  name: '',
  description: '',
  steps: [] as StepDraft[],
})
const saving = ref(false)
const error = ref('')
const isEdit = ref(false)

watch(
  () => [props.visible, props.skill] as const,
  ([visible, skill]) => {
    if (!visible) return
    error.value = ''
    saving.value = false
    if (skill) {
      isEdit.value = true
      form.name = skill.name
      form.description = skill.description || ''
      form.steps = skill.steps.map((s) => ({ tool_id: s.tool_id, note: s.note || '' }))
    } else {
      isEdit.value = false
      form.name = ''
      form.description = ''
      form.steps = [{ tool_id: 0, note: '' }]
    }
  },
  { immediate: true },
)

function addStep() {
  form.steps.push({ tool_id: 0, note: '' })
}

function move(i: number, dir: -1 | 1) {
  const j = i + dir
  if (j < 0 || j >= form.steps.length) return
  const [row] = form.steps.splice(i, 1)
  form.steps.splice(j, 0, row)
}

async function submit() {
  error.value = ''
  if (!form.name.trim()) return (error.value = '请填写技能名称')
  if (!form.steps.length) return (error.value = '至少需要一个步骤')
  if (form.steps.some((s) => !s.tool_id)) return (error.value = '每个步骤都需要选择一个工具')

  const payload = {
    name: form.name.trim(),
    description: form.description.trim(),
    steps: form.steps.map((s) => ({
      tool_id: s.tool_id,
      ...(s.note.trim() ? { note: s.note.trim() } : {}), // 空 note 不提交
    })),
  }

  saving.value = true
  try {
    if (isEdit.value && props.skill) {
      await updateSkill(props.skill.id, payload)
    } else {
      await createSkill(payload)
    }
    emit('saved')
    close()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    saving.value = false
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
  background: var(--surface);
  border-radius: 16px;
  width: 640px;
  max-width: 100%;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow: hidden;
}
.modal-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 24px 0;
  flex-shrink: 0;
}
.modal-title {
  font-size: 16px;
  font-weight: 700;
  flex: 1;
}
.modal-sub {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 400;
  margin-top: 2px;
}
.close {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: none;
  background: none;
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
  flex-shrink: 0;
}
.close:hover {
  background: #f5f5f4;
  color: var(--text);
}

.modal-body {
  padding: 16px 24px 4px;
  overflow-y: auto;
}

.field { margin-bottom: 12px; }
.field-label {
  font-size: 12.5px;
  font-weight: 600;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.field-label .req { color: var(--orange); }
.field-label .opt {
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 400;
}
.input,
.textarea,
.select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text);
  font-family: inherit;
  outline: none;
  background: var(--surface);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.input:focus,
.textarea:focus,
.select:focus {
  border-color: var(--orange);
  box-shadow: 0 0 0 3px rgba(217, 119, 6, 0.12);
}
.textarea {
  resize: none;
  height: 54px;
  line-height: 1.55;
}
.select {
  appearance: none;
  cursor: pointer;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' fill='none' stroke='%2378716c' stroke-width='1.5' stroke-linecap='round'/></svg>");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 32px;
}
.field-hint {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 5px;
}
.field-hint.warn { color: var(--orange-hover); }

.steps-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.steps-head .field-label { margin-bottom: 0; }
.steps-head .count {
  font-size: 11px;
  background: var(--orange-light);
  color: var(--orange-hover);
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.step-row {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 8px 12px;
  display: flex;
  gap: 10px;
  align-items: flex-start;
  background: var(--surface);
}
.step-row:hover { border-color: var(--orange-border); }
.step-no {
  width: 21px;
  height: 21px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--orange-light);
  color: var(--orange-hover);
  font-size: 11.5px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 5px;
}
.step-fields {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.step-ops {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
  margin-top: 3px;
}
.icon-btn {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
}
.icon-btn:hover {
  background: #f5f5f4;
  color: var(--text);
}
.icon-btn:disabled {
  opacity: 0.3;
  cursor: default;
}
.icon-btn:disabled:hover {
  background: none;
  color: var(--text-secondary);
}
.icon-btn.danger:hover {
  background: var(--red-bg);
  color: var(--red-text);
}

.add-step {
  width: 100%;
  border: 1.5px dashed #d6d3d1;
  border-radius: 12px;
  background: none;
  padding: 9px;
  font-size: 12.5px;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
  font-weight: 600;
  transition: border-color 0.15s, color 0.15s;
}
.add-step:hover {
  border-color: var(--orange);
  color: var(--orange);
}

.use-tip {
  margin-top: 12px;
  padding: 9px 12px;
  background: var(--orange-light);
  border-radius: 10px;
  font-size: 12px;
  color: var(--orange-hover);
  line-height: 1.55;
}
.use-tip b { font-weight: 700; }

.error-bar {
  margin: 8px 24px 0;
  padding: 9px 12px;
  background: var(--red-bg);
  border: 1px solid var(--red-border);
  border-radius: 10px;
  color: var(--red-text);
  font-size: 12.5px;
  flex-shrink: 0;
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 24px 18px;
  flex-shrink: 0;
}
.btn {
  border: none;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.15s;
  font-family: inherit;
}
.btn-ghost {
  background: #f5f5f4;
  color: var(--text);
  padding: 10px 20px;
  font-size: 13px;
}
.btn-ghost:hover { background: #e7e5e4; }
.btn-save {
  background: var(--orange);
  color: #fff;
  padding: 10px 22px;
  font-size: 13px;
}
.btn-save:hover:not(:disabled) { background: var(--orange-hover); }
.btn-save:disabled { opacity: 0.6; cursor: wait; }
</style>
