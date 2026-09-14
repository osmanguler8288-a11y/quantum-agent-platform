<template>
  <div v-if="visible" class="overlay" @click.self="close">
    <div class="modal">
      <div class="modal-header">
        <h3>{{ isEdit ? `编辑工具 · ${form.display_name}` : '新增工具' }}</h3>
        <button class="close" @click="close">×</button>
      </div>

      <p class="hint">
        修改后立即生效，正在运行的任务不受影响。带 <b>*</b> 为必填项。
      </p>

      <div class="body">
        <!-- 工具标识：内置工具不可改 -->
        <label class="field">
          <span class="label">工具标识 <b>*</b></span>
          <input
            v-model="form.name"
            :disabled="isBuiltin"
            placeholder="小写字母开头，如 orca_casscf"
          />
          <span v-if="isBuiltin" class="sub">内置工具的执行契约由代码定义，标识不可修改</span>
          <span v-else class="sub">Agent 调用时用的名字，创建后不可修改</span>
        </label>

        <label class="field">
          <span class="label">工具名称 <b>*</b></span>
          <input v-model="form.display_name" placeholder="展示给用户的名称" />
        </label>

        <label class="field">
          <span class="label">分类 <b>*</b></span>
          <select v-model.number="form.category_id">
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </label>

        <label class="field">
          <span class="label">工具介绍 <b>*</b></span>
          <textarea v-model="form.user_description" rows="3" placeholder="支持 Markdown，将展示在工具详情页" />
        </label>

        <div class="field">
          <span class="label">来源类型</span>
          <div class="segmented">
            <!-- ⚠️ 「内置」只在编辑既有内置工具时可见/可选。
                 新增时禁用 —— 内置工具的执行函数来自代码，接口创建的 builtin 工具
                 永远调不通，还会让每次 registry 重建报错。后端会返回 400 兜底。 -->
            <button
              v-if="isEdit"
              type="button"
              :class="{ on: form.source === 'builtin' }"
              :disabled="isBuiltin"
              @click="form.source = 'builtin'"
            >内置</button>
            <button
              type="button"
              :class="{ on: form.source === 'mcp' }"
              @click="form.source = 'mcp'"
            >MCP 接入</button>
          </div>
          <span v-if="isBuiltin" class="sub">内置工具的执行函数来自代码，来源不可修改</span>
          <span v-else-if="!isEdit" class="sub">通过界面只能接入外部 MCP 服务；内置工具由平台代码定义</span>
        </div>

        <label v-if="form.source === 'mcp'" class="field">
          <span class="label">MCP 服务地址 <b>*</b></span>
          <input v-model="form.endpoint" :disabled="isBuiltin" placeholder="mcp://calc-cluster/gaussian16" />
        </label>

        <div class="field">
          <span class="label">标签</span>
          <div class="tag-editor">
            <span v-for="(t, i) in form.tags" :key="t + i" class="tag">
              {{ t }}<button type="button" @click="form.tags.splice(i, 1)">×</button>
            </span>
            <input
              v-model="tagDraft"
              class="tag-input"
              placeholder="输入后回车添加"
              @keydown.enter.prevent="addTag"
            />
          </div>
        </div>

        <label class="field">
          <span class="label">参数定义（JSON Schema）</span>
          <textarea
            v-model="parametersText"
            rows="4"
            class="mono"
            :disabled="isBuiltin"
            placeholder='{"type":"object","properties":{"nroots":{"type":"integer","description":"态数"}},"required":[]}'
          />
          <span v-if="isBuiltin" class="sub">内置工具的参数契约来自代码，不可修改</span>
        </label>

        <label class="field">
          <span class="label">参数模板（JSON）</span>
          <textarea
            v-model="templateText"
            rows="3"
            class="mono"
            placeholder='{"nroots": 5}'
          />
          <span class="sub">预设默认值，key 必须在参数定义中声明</span>
        </label>

        <label v-if="!isEdit" class="field checkbox">
          <input v-model="enableNow" type="checkbox" />
          <span>保存后立即启用 —— 该工具将出现在 Agent 可调用工具列表中</span>
        </label>
      </div>

      <div v-if="error" class="error-bar">{{ error }}</div>

      <div class="modal-footer">
        <button class="btn btn-ghost" @click="close">取消</button>
        <button class="btn btn-primary" :disabled="saving" @click="submit">
          {{ saving ? '保存中…' : isEdit ? '保存修改' : '创建工具' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  createTool, updateTool,
  type Category, type Tool, type ToolPayload,
} from '@/api/tools'

const props = defineProps<{
  visible: boolean
  tool: Tool | null
  categories: Category[]
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved', id: number): void }>()

const isEdit = computed(() => props.tool !== null)
const isBuiltin = computed(() => props.tool?.source === 'builtin')

const form = ref<{
  name: string
  display_name: string
  category_id: number
  user_description: string
  source: 'builtin' | 'mcp'
  endpoint: string
  tags: string[]
}>(blank())

const parametersText = ref('')
const templateText = ref('')
const tagDraft = ref('')
const enableNow = ref(true)
const saving = ref(false)
const error = ref('')

function blank() {
  return {
    name: '',
    display_name: '',
    category_id: props.categories[0]?.id ?? 0,
    user_description: '',
    source: 'mcp' as 'builtin' | 'mcp',
    endpoint: '',
    tags: [] as string[],
  }
}

// 弹窗打开时按「新增 / 编辑」两种模式回填
watch(
  () => [props.visible, props.tool] as const,
  ([visible, tool]) => {
    if (!visible) return
    error.value = ''
    tagDraft.value = ''
    enableNow.value = true
    if (tool) {
      form.value = {
        name: tool.name,
        display_name: tool.display_name,
        category_id: tool.category_id,
        user_description: tool.user_description,
        source: tool.source,
        endpoint: tool.endpoint || '',
        tags: [...tool.tags],
      }
      parametersText.value = JSON.stringify(tool.parameters ?? {}, null, 2)
      templateText.value = JSON.stringify(tool.param_template ?? {}, null, 2)
    } else {
      form.value = blank()
      parametersText.value = ''
      templateText.value = ''
    }
  },
  { immediate: true },
)

function addTag() {
  const t = tagDraft.value.trim()
  if (t && !form.value.tags.includes(t)) form.value.tags.push(t)
  tagDraft.value = ''
}

function parseJson(text: string, label: string): Record<string, any> | null {
  const s = text.trim()
  if (!s) return {}
  try {
    const v = JSON.parse(s)
    if (typeof v !== 'object' || v === null || Array.isArray(v)) {
      error.value = `${label}必须是一个 JSON 对象`
      return null
    }
    return v
  } catch (e) {
    error.value = `${label}不是合法 JSON：${(e as Error).message}`
    return null
  }
}

/**
 * 前端预校验：与后端 app/schemas/tool.py 的核心规则保持一致，
 * 目的是让用户在提交前就看到问题，而不是等后端 422。
 * ⚠️ 后端仍是最终权威，这里不做穷举。
 */
function validateTemplate(params: Record<string, any>, template: Record<string, any>): string | null {
  if (!Object.keys(template).length) return null
  const propsMap = (params.properties ?? {}) as Record<string, any>
  if (!Object.keys(propsMap).length) {
    return '未定义任何参数，参数模板应为空'
  }
  for (const [k, v] of Object.entries(template)) {
    if (!(k in propsMap)) return `参数模板中的「${k}」未在参数定义中声明`
    const want = propsMap[k]?.type
    // ⚠️ 先判布尔：JS 里 typeof true === 'boolean'，但后端 Python 里
    //    isinstance(True, int) 为真，所以两边都必须显式排除布尔
    const isBool = typeof v === 'boolean'
    const isNum = typeof v === 'number' && !isBool
    const isStr = typeof v === 'string'
    const isArr = Array.isArray(v)
    const isObj = v !== null && typeof v === 'object' && !isArr
    const ok =
      (want === 'string' && isStr) ||
      (want === 'integer' && isNum && Number.isInteger(v)) ||
      (want === 'number' && isNum) ||
      (want === 'boolean' && isBool) ||
      (want === 'array' && isArr) ||
      (want === 'object' && isObj)
    if (!ok) return `参数模板「${k}」类型不匹配：期望 ${want}`
  }
  return null
}

async function submit() {
  error.value = ''
  const f = form.value

  if (!isEdit.value && !f.name.trim()) return (error.value = '请填写工具标识')
  if (!f.display_name.trim()) return (error.value = '请填写工具名称')
  if (!f.user_description.trim()) return (error.value = '请填写工具介绍')
  if (f.source === 'mcp' && !f.endpoint.trim()) {
    return (error.value = '来源为 MCP 接入时，必须填写 MCP 服务地址')
  }

  const params = parseJson(parametersText.value, '参数定义')
  if (params === null) return
  const template = parseJson(templateText.value, '参数模板')
  if (template === null) return

  const mismatch = validateTemplate(params, template)
  if (mismatch) return (error.value = mismatch)

  const payload: ToolPayload = {
    display_name: f.display_name.trim(),
    category_id: f.category_id,
    user_description: f.user_description.trim(),
    tags: f.tags,
    param_template: template,
  }
  if (!isEdit.value) {
    payload.name = f.name.trim()
    payload.source = f.source
    payload.endpoint = f.source === 'mcp' ? f.endpoint.trim() : null
    payload.status = enableNow.value ? 'enabled' : 'disabled'
  }
  // 内置工具的契约字段由代码定义，不能放进 payload（后端会返回 403）
  if (!isBuiltin.value) {
    payload.parameters = params
    if (isEdit.value) payload.endpoint = f.source === 'mcp' ? f.endpoint.trim() : null
  }

  saving.value = true
  try {
    const saved = isEdit.value && props.tool
      ? await updateTool(props.tool.id, payload)
      : await createTool(payload)
    emit('saved', saved.id)
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
  width: 640px;
  max-width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  padding: 18px 20px 12px;
}
.modal-header h3 {
  flex: 1;
  font-size: 16px;
  font-weight: 700;
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
.close:hover {
  background: #f5f5f4;
  color: var(--text);
}

.hint {
  margin: 0 20px 12px;
  padding: 9px 12px;
  background: var(--orange-light);
  border-radius: 10px;
  font-size: 12px;
  color: var(--amber-text);
}

.body {
  padding: 0 20px 8px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field.checkbox {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text);
}
.label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}
.label b {
  color: var(--red-text);
}
.sub {
  font-size: 11.5px;
  color: var(--text-secondary);
}

input[type='text'],
input:not([type]),
select,
textarea {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 13px;
  font-family: inherit;
  color: var(--text);
  background: var(--surface);
  outline: none;
  width: 100%;
}
input:not([type]):focus,
input[type='text']:focus,
select:focus,
textarea:focus {
  border-color: var(--orange);
}
input:disabled,
textarea:disabled {
  background: #fafaf9;
  color: var(--text-secondary);
  cursor: not-allowed;
}
textarea {
  resize: vertical;
  line-height: 1.5;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.5px;
}

.segmented {
  display: inline-flex;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  width: fit-content;
}
.segmented button {
  border: none;
  background: none;
  font-size: 12.5px;
  padding: 7px 18px;
  cursor: pointer;
  color: var(--text-secondary);
  font-family: inherit;
}
.segmented button.on {
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px var(--border);
}
.segmented button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.tag-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 7px 10px;
  min-height: 40px;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 2px 6px 2px 8px;
  border-radius: 6px;
  color: var(--text-secondary);
}
.tag button {
  border: none;
  background: none;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1;
  padding: 0;
}
.tag button:hover {
  color: var(--red-text);
}
.tag-input {
  border: none !important;
  outline: none;
  flex: 1;
  min-width: 110px;
  font-size: 12.5px;
  padding: 4px 0 !important;
  background: transparent !important;
}

.error-bar {
  margin: 8px 20px 0;
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
  padding: 14px 20px 18px;
}
.btn {
  padding: 9px 20px;
  font-size: 13px;
}
.btn-ghost {
  background: #f5f5f4;
  color: var(--text);
}
.btn-ghost:hover {
  background: #e7e5e4;
}
</style>
