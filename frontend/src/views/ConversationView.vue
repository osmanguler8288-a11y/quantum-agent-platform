<template>
  <div class="conversations">
    <Sidebar @show-memory="noop" @logout="onLogout" />

    <div class="main">
      <!-- 页头 -->
      <div class="page-header">
        <div class="row1">
          <div>
            <div class="page-title">对话管理</div>
            <div class="page-sub">查看、重命名、归档或删除历史对话；正在进行的对话会持续显示在最上方</div>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <span class="s-icon">🔍</span>
              <input
                v-model="keyword"
                placeholder="搜索对话标题或消息内容…"
                @input="onSearchInput"
              />
            </div>
            <button class="btn btn-primary btn-add" @click="newVisible = true">＋ 新建对话</button>
          </div>
        </div>

        <div class="tabs-row">
          <button
            v-for="t in tabs"
            :key="t.value"
            class="tab"
            :class="{ active: tab === t.value }"
            @click="setTab(t.value)"
          >
            {{ t.label }}
            <span v-if="counts !== null" class="num">{{ counts[t.value] }}</span>
          </button>
          <div class="tabs-spacer" />
          <span class="result-count">按最近活动排序</span>
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
          <div class="empty-icon">💬</div>
          <template v-if="isConvEmpty">
            <p>还没有对话</p>
            <span class="empty-hint">新建一个对话开始使用，历史对话会自动出现在这里</span>
            <button class="btn btn-primary empty-cta" @click="newVisible = true">＋ 新建对话</button>
          </template>
          <template v-else>
            <p>没有匹配的对话</p>
            <span class="empty-hint">试试换个关键词，或切换到「全部」查看全部对话</span>
          </template>
        </div>

        <template v-else>
          <div class="conv-list">
            <ConversationRow
              v-for="c in list.items"
              :key="c.id"
              :conv="c"
              @open="openInChat"
              @detail="openDetail"
              @edit="openEdit"
              @remove="askRemove"
            />
          </div>

          <div class="pagination">
            <span class="page-info">共 {{ list.total }} 条 · 每页 {{ PAGE_SIZE }} 条</span>
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
    <NewConvModal
      :visible="newVisible"
      @close="newVisible = false"
      @created="onCreated"
      @create-local="onCreateLocal"
    />

    <EditConvModal
      :visible="editVisible"
      :conv="editing"
      @close="editVisible = false"
      @saved="onSaved"
      @remove="askRemoveFromEdit"
    />

    <ConvDetailModal
      :visible="detailVisible"
      :conv-id="detailId"
      @close="detailVisible = false"
      @edit="openEditFromDetail"
      @remove="askRemoveFromDetail"
      @continue="openInChat"
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
      <template #message>
        <template v-if="confirm.messages !== null">
          将同时删除该对话的全部 <b>{{ confirm.messages }} 条消息</b>，删除后无法恢复、也无法继续追问。
        </template>
        <template v-else>{{ confirm.message }}</template>
      </template>
    </ConfirmDialog>
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
import ConversationRow from '@/components/conv/ConversationRow.vue'
import NewConvModal from '@/components/conv/NewConvModal.vue'
import EditConvModal from '@/components/conv/EditConvModal.vue'
import ConvDetailModal from '@/components/conv/ConvDetailModal.vue'
import ConfirmDialog from '@/components/tools/ConfirmDialog.vue'
import { isApiNotFound } from '@/api/client'
import {
  deleteConversation, fetchConversations,
  type ConvDetail, type ConvSummary, type ConvTab, type ConvTabCounts, type ConvListResponse,
} from '@/api/conversation'

const router = useRouter()
const auth = useAuthStore()
const chat = useChatStore()
const session = useSessionStore()
const conversation = useConversationStore()

const tabs: { label: string; value: ConvTab }[] = [
  { label: '全部', value: 'all' },
  { label: '进行中', value: 'active' },
  { label: '已归档', value: 'archived' },
]

const PAGE_SIZE = 10 // 与设计稿主列表一致

const list = ref<ConvListResponse>({ items: [], total: 0, page: 1, page_size: PAGE_SIZE })
/** Tab 计数：接口未下发时由前端补齐；完全拿不到（如 404）时隐藏数字 */
const counts = ref<ConvTabCounts | null>(null)

const keyword = ref('')
const tab = ref<ConvTab>('all')
const page = ref(1)

const loading = ref(false)
const error = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(list.value.total / PAGE_SIZE)))
const pageNumbers = computed(() => {
  const n = totalPages.value
  const cur = page.value
  const start = Math.max(1, Math.min(cur - 2, n - 4))
  const end = Math.min(n, start + 4)
  return Array.from({ length: end - start + 1 }, (_, i) => start + i)
})

/** 无任何筛选且总数为 0 → 整库为空（区别于「筛选无结果」） */
const isConvEmpty = computed(
  () => !keyword.value.trim() && tab.value === 'all' && list.value.total === 0,
)

// ─── 数据加载 ────────────────────────────────────────
const EMPTY_LIST: ConvListResponse = { items: [], total: 0, page: 1, page_size: PAGE_SIZE }

/**
 * 拉取列表。
 * - 404（后端暂无 /api/conversations 路由，或没有对话）→ 降级为空列表，显示「还没有对话」
 * - 其他错误（500 / 断网）→ 错误态 + 重试
 */
async function fetchPageData() {
  const resp = await fetchConversations({
    keyword: keyword.value.trim() || undefined,
    tab: tab.value,
    page: page.value,
    page_size: PAGE_SIZE,
  }).catch((e) => {
    if (isApiNotFound(e)) return null
    throw e
  })

  if (resp === null) {
    list.value = EMPTY_LIST
    counts.value = null
    return
  }

  list.value = resp

  // Tab 计数：优先用接口下发；没有就并行发 3 个轻量请求补齐（page_size=1 只为拿 total）
  if (resp.counts) {
    counts.value = resp.counts
  } else {
    const [all, active, archived] = await Promise.all(
      (['all', 'active', 'archived'] as ConvTab[]).map((t) =>
        t === tab.value
          ? Promise.resolve(resp.total)
          : fetchConversations({ tab: t, page: 1, page_size: 1 })
              .then((r) => r.total)
              .catch(() => null),
      ),
    )
    counts.value =
      all === null && active === null && archived === null
        ? null
        : { all: all ?? 0, active: active ?? 0, archived: archived ?? 0 }
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    await fetchPageData()
  } catch (e) {
    error.value = `对话列表加载失败：${(e as Error).message}`
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

function setTab(t: ConvTab) {
  if (tab.value === t) return
  tab.value = t
  page.value = 1
  load()
}

function goPage(p: number) {
  if (p < 1 || p > totalPages.value || p === page.value) return
  page.value = p
  load()
}

// ─── 新建 ────────────────────────────────────────────
const newVisible = ref(false)

function onCreated(conv: ConvDetail) {
  // 创建成功 → 同步到侧边栏会话列表并打开
  openInChat(conv)
}

/** 后端暂无 /api/conversations 路由（404）→ 以本地新对话进入聊天页，不报错 */
function onCreateLocal() {
  conversation.newConversation()
  session.clear()
  chat.clear()
  router.push({ name: 'chat' })
}

// ─── 编辑 ────────────────────────────────────────────
const editVisible = ref(false)
const editing = ref<ConvSummary | null>(null)

function openEdit(conv: ConvSummary) {
  editing.value = conv
  editVisible.value = true
}

function openEditFromDetail(conv: ConvDetail) {
  detailVisible.value = false
  editing.value = conv
  editVisible.value = true
}

function askRemoveFromEdit(conv: ConvSummary) {
  editVisible.value = false
  askRemove(conv)
}

/** 保存后：同步侧边栏（改名的更新标题；归档的从侧边栏移除）并刷新列表 */
function onSaved(conv: ConvSummary) {
  if (conv.archived) conversation.remove(conv.id)
  else conversation.upsert(conv)
  load()
}

// ─── 详情 ────────────────────────────────────────────
const detailVisible = ref(false)
const detailId = ref<number | null>(null)

function openDetail(conv: ConvSummary) {
  detailId.value = conv.id
  detailVisible.value = true
}

function askRemoveFromDetail(conv: ConvDetail) {
  detailVisible.value = false
  askRemove(conv)
}

// ─── 继续对话：桥接回聊天页（会话 store 用字符串 id）───
function openInChat(c: { id: number; title: string; updated_at: string }) {
  const sid = conversation.upsert(c)
  conversation.switchTo(sid)
  session.setSession(sid)
  chat.loadConversation(sid, c.title)
  router.push({ name: 'chat' })
}

// ─── 删除确认（复用通用 ConfirmDialog）────────────────
const confirm = reactive({
  visible: false,
  title: '',
  message: '',
  warning: '',
  warningTone: 'amber' as 'red' | 'amber',
  confirmText: '确认删除',
  busy: false,
  /** 待删对话的消息数（加粗展示），拿不到时为 null */
  messages: null as number | null,
  target: null as ConvSummary | null,
})

function askRemove(conv: ConvSummary) {
  confirm.visible = true
  confirm.target = conv
  confirm.busy = false
  confirm.confirmText = '确认删除'
  confirm.title = `删除对话「${conv.title}」？`
  confirm.messages = conv.message_count || null
  confirm.message = conv.message_count
    ? `将同时删除该对话的全部 ${conv.message_count} 条消息，删除后无法恢复、也无法继续追问。`
    : '删除后无法恢复、也无法继续追问。'
  // 与设计稿 05 一致：琥珀色提醒「建议改为归档」
  confirm.warning = '若只是不再使用，建议改为归档——从列表移除但保留记录，随时可恢复。'
  confirm.warningTone = 'amber'
}

async function onConfirm() {
  const conv = confirm.target
  if (!conv) return
  confirm.busy = true
  try {
    await deleteConversation(conv.id)
    confirm.visible = false
    // 同步移除侧边栏会话列表里的同名会话
    conversation.remove(conv.id)
    await load()
  } catch (e) {
    alert(`删除失败：${(e as Error).message}`)
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

onMounted(load)
</script>

<style scoped>
.conversations {
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
  width: 280px;
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

.tabs-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 14px 0 0;
  border-bottom: 1px solid var(--border);
  margin-top: 14px;
}
.tab {
  border: none;
  background: none;
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text-secondary);
  font-family: inherit;
  border-radius: 8px 8px 0 0;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
}
.tab:hover {
  color: var(--text);
}
.tab.active {
  color: var(--orange);
  font-weight: 700;
  box-shadow: inset 0 -2px 0 var(--orange);
}
.tab .num {
  font-size: 11px;
  background: #f5f5f4;
  color: var(--text-secondary);
  padding: 1px 7px;
  border-radius: 10px;
  font-weight: 600;
}
.tab.active .num {
  background: var(--orange-light);
  color: var(--orange-hover);
}
.tabs-spacer {
  flex: 1;
}
.result-count {
  font-size: 12px;
  color: var(--text-secondary);
  padding-bottom: 8px;
}

.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.conv-list {
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
