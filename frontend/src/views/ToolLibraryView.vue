<template>
  <div class="tool-library">
    <Sidebar @show-memory="noop" @logout="onLogout" />

    <div class="main">
      <!-- 页头 -->
      <div class="page-header">
        <div class="row1">
          <div>
            <div class="page-title">工具库</div>
            <div class="page-sub">管理平台内置与外部接入的计算工具，配置参数后可在对话中直接调用</div>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <span class="s-icon">🔍</span>
              <input
                v-model="keyword"
                placeholder="搜索工具名称 / 描述 / 标签…"
                @input="onSearchInput"
              />
            </div>
            <button class="btn btn-ghost btn-add" @click="reload">刷新</button>
            <button class="btn btn-primary btn-add" @click="openCreate">＋ 新增工具</button>
          </div>
        </div>

        <div class="filter-row">
          <button class="chip" :class="{ active: !category }" @click="setCategory('')">
            全部 <span class="num">{{ totalAll }}</span>
          </button>
          <button
            v-for="c in categories"
            :key="c.id"
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
            共 {{ list.total }} 个工具 · 已启用 {{ list.enabled_count }} 个
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
          <div class="empty-icon">⚒</div>
          <p>没有匹配的工具</p>
          <span class="empty-hint">试试换个关键词，或点右上角「新增工具」接入一个 MCP 服务</span>
        </div>

        <template v-else>
          <div class="tool-grid">
            <ToolCard
              v-for="t in list.items"
              :key="t.id"
              :tool="t"
              :busy="busyId === t.id"
              @detail="openDetail"
              @edit="openEdit"
              @remove="askRemove"
              @restore="doRestore"
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
    <ToolEditorModal
      :visible="editorVisible"
      :tool="editing"
      :categories="categories"
      @close="editorVisible = false"
      @saved="onSaved"
    />

    <ToolDetailModal
      :visible="detailVisible"
      :tool="detail"
      @close="detailVisible = false"
      @edit="openEditFromDetail"
      @remove="askRemoveFromDetail"
    />

    <ConfirmDialog
      :visible="confirm.visible"
      :title="confirm.title"
      :message="confirm.message"
      :warning="confirm.warning"
      :busy="confirm.busy"
      @cancel="confirm.visible = false"
      @confirm="doRemove"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useConversationStore } from '@/stores/conversation'
import Sidebar from '@/components/Sidebar.vue'
import ToolCard from '@/components/tools/ToolCard.vue'
import ToolEditorModal from '@/components/tools/ToolEditorModal.vue'
import ToolDetailModal from '@/components/tools/ToolDetailModal.vue'
import ConfirmDialog from '@/components/tools/ConfirmDialog.vue'
import {
  deleteTool, fetchCategories, fetchTool, fetchTools, restoreTool, setToolStatus,
  type Category, type Tool, type ToolListResponse,
} from '@/api/tools'

const router = useRouter()
const auth = useAuthStore()
const chat = useChatStore()
const session = useSessionStore()
const conversation = useConversationStore()

const statusOptions = [
  { label: '全部', value: 'all' as const },
  { label: '已启用', value: 'enabled' as const },
  { label: '已停用', value: 'disabled' as const },
]

const PAGE_SIZE = 9   // 与设计稿主列表一致

const list = ref<ToolListResponse>({ items: [], total: 0, page: 1, page_size: PAGE_SIZE, enabled_count: 0 })
const categories = ref<Category[]>([])
const totalAll = computed(() => categories.value.reduce((s, c) => s + c.count, 0))

const keyword = ref('')
const category = ref('')
const status = ref<'all' | 'enabled' | 'disabled'>('all')
const page = ref(1)

const loading = ref(false)
const error = ref('')
const busyId = ref<number | null>(null)

const totalPages = computed(() => Math.max(1, Math.ceil(list.value.total / PAGE_SIZE)))
const pageNumbers = computed(() => {
  const n = totalPages.value
  const cur = page.value
  const start = Math.max(1, Math.min(cur - 2, n - 4))
  const end = Math.min(n, start + 4)
  return Array.from({ length: end - start + 1 }, (_, i) => start + i)
})

// ─── 数据加载 ────────────────────────────────────────
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [tools, cats] = await Promise.all([
      fetchTools({
        keyword: keyword.value.trim() || undefined,
        category: category.value || undefined,
        status: status.value,
        page: page.value,
        page_size: PAGE_SIZE,
      }),
      fetchCategories(),
    ])
    list.value = tools
    categories.value = cats.items
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
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

function setStatus(s: 'all' | 'enabled' | 'disabled') {
  status.value = s
  page.value = 1
  load()
}

function goPage(p: number) {
  if (p < 1 || p > totalPages.value || p === page.value) return
  page.value = p
  load()
}

// ─── 启停（乐观更新 + 失败回滚）────────────────────
async function doToggle(tool: Tool) {
  const next = tool.status === 'enabled' ? 'disabled' : 'enabled'
  const prev = tool.status
  tool.status = next              // 乐观更新
  busyId.value = tool.id
  try {
    const r = await setToolStatus(tool.id, next)
    if (!r.registry_reloaded) {
      // ⚠️ 后端明确告知「没真正作用到 Agent」时必须提示，不能静默当成功
      alert(`状态已更新，但 Agent 侧的工具注册表重建失败：${r.warning || '未知原因'}`)
    }
    await load()
  } catch (e) {
    tool.status = prev            // 回滚
    alert(`操作失败：${(e as Error).message}`)
  } finally {
    busyId.value = null
  }
}

// ─── 详情 ────────────────────────────────────────────
const detailVisible = ref(false)
const detail = ref<Tool | null>(null)

async function openDetail(tool: Tool) {
  detail.value = tool
  detailVisible.value = true
  try {
    detail.value = await fetchTool(tool.id, true, 5)
  } catch {
    /* 详情加载失败时保留列表里的基础数据 */
  }
}

function openEditFromDetail(tool: Tool) {
  detailVisible.value = false
  openEdit(tool)
}

function askRemoveFromDetail(tool: Tool) {
  detailVisible.value = false
  askRemove(tool)
}

// ─── 新增 / 编辑 ─────────────────────────────────────
const editorVisible = ref(false)
const editing = ref<Tool | null>(null)

function openCreate() {
  editing.value = null
  editorVisible.value = true
}

function openEdit(tool: Tool) {
  editing.value = tool
  editorVisible.value = true
}

async function onSaved() {
  await load()
}

// ─── 删除 / 恢复 ─────────────────────────────────────
const confirm = reactive({
  visible: false,
  title: '',
  message: '',
  warning: '',
  busy: false,
  target: null as Tool | null,
})

function askRemove(tool: Tool) {
  const n = tool.invocation_count
  confirm.visible = true
  confirm.target = tool
  confirm.busy = false
  confirm.title = `删除工具「${tool.display_name}」？`
  confirm.message = '删除后 Agent 将无法再调用该工具，历史调用记录与产出文件仍会保留。此操作可在 7 天内恢复。'
  confirm.warning = n > 0 ? `该工具累计被调用过 ${n} 次，删除可能影响相关技能的正常运行。` : ''
}

async function doRemove() {
  const tool = confirm.target
  if (!tool) return
  confirm.busy = true
  try {
    await deleteTool(tool.id)
    confirm.visible = false
    await load()
  } catch (e) {
    alert(`删除失败：${(e as Error).message}`)
  } finally {
    confirm.busy = false
  }
}

async function doRestore(tool: Tool) {
  try {
    await restoreTool(tool.id)
    await load()
  } catch (e) {
    alert(`恢复失败：${(e as Error).message}`)
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

onMounted(load)
</script>

<style scoped>
.tool-library {
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

.tool-grid {
  flex: 1;
  overflow-y: auto;
  padding: 18px 28px 8px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  align-content: start;
}
@media (max-width: 1200px) {
  .tool-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 900px) {
  .tool-grid { grid-template-columns: 1fr; }
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
