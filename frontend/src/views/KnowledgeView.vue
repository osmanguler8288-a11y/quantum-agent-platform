<template>
  <div class="knowledge">
    <Sidebar @show-memory="noop" @logout="onLogout" />

    <div class="main">
      <!-- 页头 -->
      <div class="page-header">
        <div class="row1">
          <div>
            <div class="page-title">知识库</div>
            <div class="page-sub">上传文献、笔记与实验数据，自动分块索引后供 Agent 检索引用</div>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <span class="s-icon">🔍</span>
              <input
                v-model="keyword"
                placeholder="搜索文档名称 / 描述 / 标签…"
                @input="onSearchInput"
              />
            </div>
            <button class="btn btn-ghost btn-add" @click="askReindexAll">重建索引</button>
            <button class="btn btn-primary btn-add" @click="uploadVisible = true">＋ 上传文档</button>
          </div>
        </div>

        <div class="filter-row">
          <button class="chip" :class="{ active: !category }" @click="setCategory('')">
            全部 <span class="num">{{ totalAll }}</span>
          </button>
          <button
            v-for="c in displayCategories"
            :key="c.name"
            class="chip"
            :class="{ active: category === c.name }"
            @click="setCategory(c.name)"
          >
            {{ c.name }} <span class="num">{{ c.count }}</span>
          </button>

          <div class="divider-v" />

          <div class="status-toggle">
            <button
              v-for="s in statusOptions"
              :key="s.value"
              :class="{ on: status === s.value }"
              @click="setStatus(s.value)"
            >{{ s.label }}</button>
          </div>

          <span class="result-count">
            共 {{ stats.documents }} 篇文档 · {{ stats.chunks.toLocaleString('zh-CN') }} 个分块 · {{ formatSize(stats.size_bytes) }}
          </span>
        </div>
      </div>

      <!-- 内容区 -->
      <div class="content">
        <div v-if="loading" class="state-block">加载中…</div>
        <div v-else-if="error" class="state-block error">
          <p>{{ error }}</p>
          <button class="btn btn-ghost" @click="reload">重试</button>
        </div>
        <div v-else-if="!list.items.length" class="state-block">
          <div class="empty-icon">▤</div>
          <template v-if="isKbEmpty">
            <p>知识库还是空的</p>
            <span class="empty-hint">上传第一篇文档，自动分块索引后 Agent 就能在对话中检索引用它</span>
            <button class="btn btn-primary empty-cta" @click="uploadVisible = true">＋ 上传第一篇文档</button>
          </template>
          <template v-else>
            <p>没有匹配的文档</p>
            <span class="empty-hint">试试换个关键词，或点右上角「上传文档」把资料加入知识库</span>
          </template>
        </div>

        <template v-else>
          <div class="doc-list">
            <DocumentRow
              v-for="d in list.items"
              :key="d.id"
              :doc="d"
              :busy="busyId === d.id"
              @detail="openDetail"
              @edit="openEdit"
              @remove="askRemove"
              @reindex="doReindex"
              @toggle="doToggle"
            />
          </div>

          <div class="pagination">
            <span class="page-info">
              共 {{ list.total }} 条 · 每页 {{ PAGE_SIZE }} 条
            </span>
            <div class="pages">
              <button class="page-btn" :disabled="page <= 1" @click="goPage(page - 1)">‹</button>
              <button
                v-for="p in pageNumbers"
                :key="p"
                class="page-btn"
                :class="{ cur: p === page }"
                @click="goPage(p)"
              >{{ p }}</button>
              <button class="page-btn" :disabled="page >= totalPages" @click="goPage(page + 1)">›</button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 弹窗 -->
    <UploadDocsModal :visible="uploadVisible" @close="uploadVisible = false" @saved="onSaved" />

    <EditDocModal
      :visible="editVisible"
      :doc="editing"
      @close="editVisible = false"
      @saved="onSaved"
    />

    <DocDetailModal
      :visible="detailVisible"
      :doc="detail"
      @close="detailVisible = false"
      @edit="openEditFromDetail"
      @remove="askRemoveFromDetail"
      @reindex="doReindexFromDetail"
    />

    <ConfirmDialog
      :visible="confirm.visible"
      :title="confirm.title"
      :message="confirm.message"
      :warning="confirm.warning"
      :warning-tone="confirm.warningTone"
      :confirm-text="confirm.confirmText"
      :busy="confirm.busy"
      @cancel="confirm.visible = false"
      @confirm="onConfirm"
    >
      <!-- 删除文档时分块数按设计稿加粗强调 -->
      <template #message>
        <template v-if="confirm.chunks !== null">
          将同时删除其 <b>{{ confirm.chunks.toLocaleString('zh-CN') }} 个索引分块</b>，删除后 Agent
          检索将不再命中该文档。此操作 7 天内可在「设置 · 回收站」恢复。
        </template>
        <template v-else>{{ confirm.message }}</template>
      </template>
    </ConfirmDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useConversationStore } from '@/stores/conversation'
import Sidebar from '@/components/Sidebar.vue'
import DocumentRow from '@/components/kb/DocumentRow.vue'
import UploadDocsModal from '@/components/kb/UploadDocsModal.vue'
import EditDocModal from '@/components/kb/EditDocModal.vue'
import DocDetailModal from '@/components/kb/DocDetailModal.vue'
import ConfirmDialog from '@/components/tools/ConfirmDialog.vue'
import { isApiNotFound } from '@/api/client'
import {
  CATEGORY_NAMES,
  deleteKbDoc, fetchKbCategories, fetchKbDocs, fetchKbStats, reindexKbAll, reindexKbDoc,
  setKbDocSearchable, formatSize, type KbCategory, type KbDoc, type KbListResponse,
} from '@/api/kb'

const router = useRouter()
const auth = useAuthStore()
const chat = useChatStore()
const session = useSessionStore()
const conversation = useConversationStore()

const statusOptions = [
  { label: '全部', value: 'all' as const },
  { label: '已索引', value: 'indexed' as const },
  { label: '索引中', value: 'indexing' as const },
  { label: '失败', value: 'failed' as const },
]

const PAGE_SIZE = 10 // 与设计稿主列表一致

const list = ref<KbListResponse>({ items: [], total: 0, page: 1, page_size: PAGE_SIZE })
const categories = ref<KbCategory[]>([])
const stats = ref({ documents: 0, chunks: 0, size_bytes: 0 })
const totalAll = computed(() => categories.value.reduce((s, c) => s + c.count, 0))

/** 分类是固定分类法：接口未返回（或暂无文档）时也保持 4 个标签可见，计数为 0 */
const displayCategories = computed<KbCategory[]>(() => {
  const counts = new Map(categories.value.map((c) => [c.name, c.count]))
  return CATEGORY_NAMES.map((name) => ({ name, count: counts.get(name) ?? 0 }))
})

const keyword = ref('')
const category = ref('')
const status = ref<'all' | 'indexed' | 'indexing' | 'failed'>('all')
const page = ref(1)

const loading = ref(false)
const error = ref('')
const busyId = ref<number | null>(null)

const totalPages = computed(() => Math.max(1, Math.ceil(list.value.total / PAGE_SIZE)))

/** 无任何筛选且总数为 0 → 整库为空（区别于「筛选无结果」） */
const isKbEmpty = computed(
  () => !keyword.value.trim() && !category.value && status.value === 'all' && list.value.total === 0,
)
const pageNumbers = computed(() => {
  const n = totalPages.value
  const cur = page.value
  const start = Math.max(1, Math.min(cur - 2, n - 4))
  const end = Math.min(n, start + 4)
  return Array.from({ length: end - start + 1 }, (_, i) => start + i)
})

// ─── 数据加载 ────────────────────────────────────────
const EMPTY_LIST: KbListResponse = { items: [], total: 0, page: 1, page_size: PAGE_SIZE }

/**
 * 拉取列表 / 分类 / 统计。
 * - 列表 404（后端暂无 /api/kb 路由，或知识库无数据）→ 降级为空列表，页面显示「知识库为空」
 * - 分类 / 统计失败（含 404）→ 用兜底值，不阻塞列表渲染
 * - 列表其他错误（500 / 断网）→ 抛出，由调用方显示错误态
 */
async function fetchPageData() {
  const [docs, cats, st] = await Promise.all([
    fetchKbDocs({
      keyword: keyword.value.trim() || undefined,
      category: category.value || undefined,
      index_status: status.value,
      page: page.value,
      page_size: PAGE_SIZE,
    }).catch((e) => {
      if (isApiNotFound(e)) return null
      throw e
    }),
    fetchKbCategories().catch(() => null),
    fetchKbStats().catch(() => null),
  ])
  list.value = docs ?? EMPTY_LIST
  categories.value = cats?.items ?? []
  stats.value = st ?? { documents: list.value.total, chunks: 0, size_bytes: 0 }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    await fetchPageData()
  } catch (e) {
    error.value = `知识库加载失败：${(e as Error).message}`
  } finally {
    loading.value = false
  }
}

/** 静默刷新：轮询索引进度时不显示 loading，避免闪烁 */
async function loadSilent() {
  try {
    await fetchPageData()
  } catch {
    /* 静默失败，等下个周期 */
  }
}

function reload() {
  page.value = 1
  load()
}

// 搜索 300ms 防抖（设计稿要求）
let searchTimer: ReturnType<typeof setTimeout> | undefined
function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
}

function setCategory(name: string) {
  category.value = category.value === name ? '' : name
  page.value = 1
  load()
}

function setStatus(s: 'all' | 'indexed' | 'indexing' | 'failed') {
  status.value = s
  page.value = 1
  load()
}

function goPage(p: number) {
  if (p < 1 || p > totalPages.value || p === page.value) return
  page.value = p
  load()
}

// ─── 索引进度轮询：列表里存在「索引中」时每 1.5s 静默刷新 ──
let pollTimer: ReturnType<typeof setInterval> | undefined
function syncPolling() {
  const hasIndexing = list.value.items.some((d) => d.index_status === 'indexing')
  if (hasIndexing && pollTimer === undefined) {
    pollTimer = setInterval(loadSilent, 1500)
  } else if (!hasIndexing && pollTimer !== undefined) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
}
onBeforeUnmount(() => {
  clearInterval(pollTimer)
  pollTimer = undefined
})
/** load 之后根据结果启停轮询 */
async function loadAndSync() {
  await load()
  syncPolling()
}
async function loadSilentAndSync() {
  await loadSilent()
  syncPolling()
}

// ─── 参与检索开关（乐观更新 + 失败回滚）──────────────
async function doToggle(doc: KbDoc) {
  const next = !doc.searchable
  const prev = doc.searchable
  doc.searchable = next // 乐观更新
  busyId.value = doc.id
  try {
    await setKbDocSearchable(doc.id, next)
    await loadSilentAndSync()
  } catch (e) {
    doc.searchable = prev // 回滚
    alert(`操作失败：${(e as Error).message}`)
  } finally {
    busyId.value = null
  }
}

// ─── 详情 ────────────────────────────────────────────
const detailVisible = ref(false)
const detail = ref<KbDoc | null>(null)

function openDetail(doc: KbDoc) {
  detail.value = doc
  detailVisible.value = true
}

function openEditFromDetail(doc: KbDoc) {
  detailVisible.value = false
  openEdit(doc)
}

function askRemoveFromDetail(doc: KbDoc) {
  detailVisible.value = false
  askRemove(doc)
}

async function doReindexFromDetail(doc: KbDoc) {
  detailVisible.value = false
  await doReindex(doc)
}

// ─── 上传 / 编辑 ─────────────────────────────────────
const uploadVisible = ref(false)
const editVisible = ref(false)
const editing = ref<KbDoc | null>(null)

function openEdit(doc: KbDoc) {
  editing.value = doc
  editVisible.value = true
}

async function onSaved() {
  await loadAndSync()
}

// ─── 重建索引（单篇失败重试）─────────────────────────
async function doReindex(doc: KbDoc) {
  busyId.value = doc.id
  try {
    await reindexKbDoc(doc.id)
    await loadAndSync()
  } catch (e) {
    alert(`重建索引失败：${(e as Error).message}`)
  } finally {
    busyId.value = null
  }
}

// ─── 确认弹窗（删除 / 整库重建）──────────────────────
const confirm = reactive({
  visible: false,
  title: '',
  message: '',
  warning: '',
  warningTone: 'red' as 'red' | 'amber',
  confirmText: '确认删除',
  busy: false,
  /** 删除场景：待删除文档的索引分块数（加粗展示），非删除场景为 null */
  chunks: null as number | null,
  action: '' as 'delete' | 'reindexAll',
  target: null as KbDoc | null,
})

function askRemove(doc: KbDoc) {
  confirm.visible = true
  confirm.action = 'delete'
  confirm.target = doc
  confirm.busy = false
  confirm.confirmText = '确认删除'
  confirm.warningTone = 'red'
  confirm.title = `删除文档「${doc.name}」？`
  const chunks = doc.chunk_count ?? 0
  confirm.chunks = chunks || null
  confirm.message = chunks
    ? `将同时删除其 ${chunks.toLocaleString('zh-CN')} 个索引分块，删除后 Agent 检索将不再命中该文档。此操作 7 天内可在「设置 · 回收站」恢复。`
    : '删除后 Agent 检索将不再命中该文档。此操作 7 天内可在「设置 · 回收站」恢复。'
  confirm.warning = doc.citations_30d > 0
    ? `该文档近 30 天被检索引用 ${doc.citations_30d} 次，删除可能影响相关问答的准确性。`
    : ''
}

function askReindexAll() {
  if (!stats.value.documents) {
    alert('知识库中还没有文档')
    return
  }
  confirm.visible = true
  confirm.action = 'reindexAll'
  confirm.target = null
  confirm.busy = false
  confirm.confirmText = '开始重建'
  confirm.warningTone = 'amber'
  confirm.chunks = null
  confirm.title = '重建全部索引？'
  confirm.message = `将对知识库全部 ${stats.value.documents} 篇文档重新分块并向量化，期间已索引的分块仍可检索，重建完成后自动切换。`
  confirm.warning = '重建期间会占用较多计算资源，建议在空闲时段执行。'
}

async function onConfirm() {
  if (confirm.action === 'delete') return doRemove()
  return doReindexAll()
}

async function doRemove() {
  const doc = confirm.target
  if (!doc) return
  confirm.busy = true
  try {
    await deleteKbDoc(doc.id)
    confirm.visible = false
    await loadAndSync()
  } catch (e) {
    alert(`删除失败：${(e as Error).message}`)
  } finally {
    confirm.busy = false
  }
}

async function doReindexAll() {
  confirm.busy = true
  try {
    const r = await reindexKbAll()
    confirm.visible = false
    await loadAndSync()
    alert(`已提交 ${r.queued} 篇文档的索引重建任务`)
  } catch (e) {
    alert(`重建索引失败：${(e as Error).message}`)
  } finally {
    confirm.busy = false
  }
}

// ─── 其他 ────────────────────────────────────────────
function noop() {}

function onLogout() {
  auth.logout()
  session.clear()
  chat.clear()
  conversation.newConversation()
  router.push({ name: 'login' })
}

onMounted(loadAndSync)
</script>

<style scoped>
.knowledge {
  height: 100%;
  display: flex;
}
.main {
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg);
}

.page-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 18px 28px 0;
  flex-shrink: 0;
}
.row1 {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.page-title {
  font-size: 20px;
  font-weight: 700;
}
.page-sub {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}
.header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 9px 12px;
  width: 260px;
}
.search-box input {
  border: none;
  background: none;
  outline: none;
  font-size: 13px;
  color: var(--text);
  flex: 1;
  font-family: inherit;
  min-width: 0;
}
.s-icon {
  color: var(--text-secondary);
  font-size: 14px;
}

.btn-add {
  padding: 9px 16px;
  font-size: 13px;
}
.btn-ghost {
  background: #f5f5f4;
  color: var(--text);
}
.btn-ghost:hover {
  background: #e7e5e4;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 0;
  margin-top: 14px;
  flex-wrap: wrap;
}
.chip {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 12px;
  padding: 6px 14px;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 500;
  font-family: inherit;
  transition: background 0.12s;
}
.chip:hover {
  background: #f5f5f4;
}
.chip.active {
  background: var(--orange);
  border-color: var(--orange);
  color: #fff;
  font-weight: 600;
}
.chip .num {
  opacity: 0.65;
  margin-left: 4px;
  font-size: 11px;
}

.divider-v {
  width: 1px;
  height: 18px;
  background: var(--border);
  margin: 0 4px;
}

.status-toggle {
  display: flex;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.status-toggle button {
  border: none;
  background: none;
  font-size: 12px;
  padding: 6px 14px;
  cursor: pointer;
  color: var(--text-secondary);
  font-family: inherit;
}
.status-toggle button.on {
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px var(--border);
}

.result-count {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-secondary);
}

.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.doc-list {
  flex: 1;
  overflow-y: auto;
  padding: 14px 28px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.state-block {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 13px;
}
.state-block.error {
  color: var(--red-text);
}
.state-block .empty-icon {
  font-size: 40px;
  opacity: 0.35;
}
.empty-hint {
  font-size: 12px;
  opacity: 0.8;
}
.empty-cta {
  margin-top: 6px;
  padding: 9px 18px;
  font-size: 13px;
}

.pagination {
  flex-shrink: 0;
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: 12px 28px;
  display: flex;
  align-items: center;
  font-size: 12.5px;
}
.page-info {
  color: var(--text-secondary);
}
.pages {
  margin-left: auto;
  display: flex;
  gap: 6px;
}
.page-btn {
  min-width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  font-size: 12.5px;
  font-family: inherit;
}
.page-btn.cur {
  background: var(--orange);
  border-color: var(--orange);
  color: #fff;
  font-weight: 600;
}
.page-btn:hover:not(.cur):not(:disabled) {
  background: #f5f5f4;
}
.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
