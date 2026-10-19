<template>
  <div v-if="visible" class="descriptor-overlay" @click.self="$emit('close')">
    <section class="descriptor-panel" role="dialog" aria-modal="true" aria-labelledby="descriptor-title">
      <header>
        <div><h3 id="descriptor-title">波函数描述符分析</h3><p>上传原始波函数文件，交给 Multiwfn 分析并下载结果。</p></div>
        <button class="close" aria-label="关闭" @click="$emit('close')">×</button>
      </header>
      <form @submit.prevent="submit">
        <label>波函数文件（必选）<input ref="fchkInput" type="file" accept=".fchk,.fch" :disabled="submitting" @change="pick($event, 'fchk')" /></label>
        <label>Gaussian 输出（可选，同一次计算）<input ref="outInput" type="file" accept=".out,.log" :disabled="submitting" @change="pick($event, 'out')" /></label>
        <p class="hint">支持 .fchk/.fch；原文件完整保留，不转换成 XYZ。单个文件最多 40 MB，合计最多 64 MB。</p>
        <details>
          <summary>分析选项</summary>
          <div class="options">
            <label>Ti 原子编号<input v-model.number="tiIndex" type="number" min="1" max="200" required /></label>
            <label>配位 O 编号<input v-model="oxygen" placeholder="例如 8,9；留空自动选择" /></label>
          </div>
          <p class="hint">原子编号从 1 开始。Ti–O 几何与键级需要对应原子；其他属性取决于文件内容。</p>
          <label class="checkbox"><input v-model="basic" type="checkbox" />仅基础解析（不运行 Multiwfn 电荷和键级分析）</label>
        </details>
        <button class="btn btn-primary" :disabled="submitting || !fchk">
          {{ submitting ? '正在上传并提交…' : '开始分析' }}
        </button>
        <p v-if="submitting" class="hint">提交期间请勿重复操作。关闭窗口不会取消已提交任务。</p>
      </form>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="history">
        <label for="descriptor-history">最近任务</label>
        <select id="descriptor-history" :value="selected?.id || ''" @change="selectJob(($event.target as HTMLSelectElement).value)">
          <option value="" disabled>选择已提交的分析任务</option>
          <option v-for="job in jobs" :key="job.id" :value="job.id">{{ job.uploads.fchk?.filename }} · {{ statusLabel(job.status) }}</option>
        </select>
        <button type="button" :disabled="refreshing" @click="refresh">刷新</button>
      </div>
      <section v-if="selected" class="result">
        <div class="status"><strong>{{ statusLabel(selected.status) }}</strong><span>{{ selected.uploads.fchk?.filename }}</span></div>
        <p v-if="isActive(selected)" class="hint">每 10 秒查询一次。关闭后可在最近任务中继续查看；关闭窗口不会取消服务端任务。</p>
        <p v-if="selected.status === 'submission_unknown' || selected.status === 'submitting'" class="hint">原文件已保存。若提交长时间未确认，请联系管理员核对服务端任务，避免重复计算。</p>
        <p v-if="selected.error" class="error">{{ selected.error }}</p>
        <p v-if="selected.partial" class="warning">部分分析失败，已完成的结果仍可下载。失败项：{{ selected.failed_methods?.join('、') || '请查看方法状态及运行日志' }}</p>
        <div class="downloads">
          <button v-for="(source, kind) in selected.uploads" :key="kind" :disabled="downloading" @click="download(`source/${kind}`, source.filename)">下载原文件：{{ source.filename }}</button>
        </div>
        <div v-if="selected.status === 'completed'" class="downloads">
          <button v-for="name in resultFiles" :key="name" :disabled="downloading" @click="download(`files/${name}`, name)">{{ name }}</button>
        </div>
        <table v-if="selected.result?.methods && Object.keys(selected.result.methods).length">
          <thead><tr><th>分析方法</th><th>状态</th></tr></thead>
          <tbody><tr v-for="(method, name) in selected.result.methods" :key="name"><td>{{ name }}</td><td>{{ method.status }} {{ method.error || '' }}</td></tr></tbody>
        </table>
        <table v-if="selected.result?.descriptors">
          <thead><tr><th>描述符</th><th>值（单位见字段名及结果文件）</th></tr></thead>
          <tbody><tr v-for="(value, name) in selected.result.descriptors" :key="name"><td>{{ name }}</td><td>{{ value == null ? '未提供' : typeof value === 'object' ? JSON.stringify(value) : value }}</td></tr></tbody>
        </table>
        <details v-if="['completed', 'failed', 'interrupted'].includes(selected.status)">
          <summary>分析日志</summary>
          <div class="downloads"><button v-for="name in logFiles" :key="name" :disabled="downloading" @click="download(`files/${name}`, name)">{{ name }}</button></div>
          <p class="hint">仅已生成的日志可下载，未执行的方法可能没有对应日志。</p>
        </details>
      </section>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { DescriptorApiError, downloadDescriptorFile, getDescriptorJob, listDescriptorJobs, submitDescriptorJob, type DescriptorJob } from '@/api/descriptors'

const props = defineProps<{ visible: boolean }>()
defineEmits<{ (e: 'close'): void }>()
const fchk = ref<File>()
const out = ref<File>()
const fchkInput = ref<HTMLInputElement>()
const outInput = ref<HTMLInputElement>()
const tiIndex = ref(1)
const oxygen = ref('')
const basic = ref(false)
const submitting = ref(false)
const refreshing = ref(false)
const downloading = ref(false)
const error = ref('')
const jobs = ref<DescriptorJob[]>([])
const selected = ref<DescriptorJob>()
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
const resultFiles = ['descriptors.json', 'summary.csv', 'charges.csv']
const logFiles = computed(() => ['worker.log', ...Object.keys(selected.value?.result?.methods || {}).map(name => `${name}.log`)])
const isActive = (job: DescriptorJob) => ['queued', 'running', 'submitting'].includes(job.status)
const statusLabel = (status: string) => ({ submitting: '提交中', queued: '排队中', running: '分析中', completed: '分析完成', failed: '分析失败', interrupted: '任务中断', rejected: '任务被拒绝', submission_failed: '提交失败', submission_unknown: '提交结果待确认' }[status] || status)

function pick(event: Event, kind: 'fchk' | 'out') {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  error.value = ''
  if (kind === 'fchk') fchk.value = undefined
  else out.value = undefined
  if (!file) return
  const suffix = file.name.split('.').pop()?.toLowerCase()
  if (!(kind === 'fchk' ? ['fchk', 'fch'] : ['out', 'log']).includes(suffix || '') || file.size === 0 || file.size > 40 * 1048576) {
    error.value = '请选择格式正确、非空且不超过 40 MB 的文件'
    input.value = ''
    return
  }
  if (kind === 'fchk') fchk.value = file
  else out.value = file
}

function remember(job: DescriptorJob) {
  jobs.value = [job, ...jobs.value.filter(item => item.id !== job.id)].sort((a, b) => b.created_at.localeCompare(a.created_at))
  selected.value = job
}

function schedule() {
  clearTimeout(timer)
  if (props.visible && selected.value && isActive(selected.value)) timer = setTimeout(refreshSelected, 10000)
}

async function refreshSelected() {
  const id = selected.value?.id
  const version = generation
  if (!id) return
  try {
    const job = await getDescriptorJob(id)
    if (version === generation && selected.value?.id === id) remember(job)
  } catch (e) {
    if (version === generation && selected.value?.id === id) error.value = (e as Error).message
  } finally { if (version === generation) schedule() }
}

async function selectJob(id: string) {
  generation++
  clearTimeout(timer)
  error.value = ''
  selected.value = jobs.value.find(job => job.id === id)
  await refreshSelected()
}

async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    const page = await listDescriptorJobs()
    jobs.value = page.items
    if (!selected.value && page.items.length) selected.value = page.items[0]
    await refreshSelected()
  } catch (e) { error.value = (e as Error).message }
  finally { refreshing.value = false }
}

async function submit() {
  if (!fchk.value || submitting.value) return
  if (fchk.value.size + (out.value?.size || 0) > 64 * 1048576) {
    error.value = '两个文件合计不能超过 64 MB'
    return
  }
  generation++
  clearTimeout(timer)
  submitting.value = true
  error.value = ''
  try {
    remember(await submitDescriptorJob(fchk.value, out.value, tiIndex.value, oxygen.value, basic.value))
    clearFiles()
  } catch (e) {
    if (e instanceof DescriptorApiError && e.job) {
      remember(e.job)
      if (e.job.status === 'submission_unknown') clearFiles()
    }
    error.value = (e as Error).message
  } finally { submitting.value = false; schedule() }
}

function clearFiles() {
  fchk.value = undefined
  out.value = undefined
  if (fchkInput.value) fchkInput.value.value = ''
  if (outInput.value) outInput.value.value = ''
}

async function download(path: string, filename: string) {
  if (!selected.value || downloading.value) return
  downloading.value = true
  error.value = ''
  try { await downloadDescriptorFile(selected.value.id, path, filename) }
  catch (e) { error.value = (e as Error).message }
  finally { downloading.value = false }
}

watch(() => props.visible, visible => {
  generation++
  clearTimeout(timer)
  if (visible) { error.value = ''; void refresh() }
})
onBeforeUnmount(() => { generation++; clearTimeout(timer) })
</script>

<style scoped>
.descriptor-overlay { position: fixed; inset: 0; z-index: 1100; background: #0006; display: flex; align-items: center; justify-content: center; padding: 20px; }
.descriptor-panel { background: var(--surface); border-radius: 16px; width: 760px; max-width: 100%; max-height: 90vh; overflow: auto; padding: 24px; }
header, .history, .status, .options { display: flex; gap: 12px; align-items: center; }
header { justify-content: space-between; align-items: flex-start; margin-bottom: 18px; }
h3 { margin: 0 0 6px; font-size: 18px; }
header p, .hint { font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.close { border: 0; background: none; font-size: 24px; cursor: pointer; }
form { display: grid; gap: 12px; }
label { display: grid; gap: 6px; font-size: 13px; }
input, select { max-width: 100%; padding: 8px; border: 1px solid var(--border); border-radius: 7px; background: var(--surface); color: var(--text); }
.options { flex-wrap: wrap; margin: 12px 0; }
.checkbox { display: flex; align-items: center; }
.history { border-top: 1px solid var(--border); padding-top: 18px; margin-top: 20px; flex-wrap: wrap; }
.history select { flex: 1; min-width: 180px; }
button { cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .55; }
.downloads { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
.downloads button, .history button { background: var(--surface); border: 1px solid var(--border); border-radius: 7px; padding: 7px 10px; overflow-wrap: anywhere; }
.result { margin-top: 16px; }
.status { flex-wrap: wrap; font-size: 13px; }
.status strong { color: var(--orange); }
.error { color: var(--red-text); font-size: 13px; overflow-wrap: anywhere; }
.warning { color: #92400e; background: #fffbeb; padding: 10px; border-radius: 8px; font-size: 13px; }
table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 12px; }
td, th { text-align: left; padding: 8px; border-bottom: 1px solid var(--border); overflow-wrap: anywhere; }
summary { cursor: pointer; font-size: 13px; }
</style>
