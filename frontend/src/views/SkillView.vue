<template>
  <div class="skills">
    <Sidebar @show-memory="noop" @logout="onLogout" />

    <div class="main">
      <!-- 页头 -->
      <div class="page-header">
        <div class="row1">
          <div>
            <div class="page-title">技能中心</div>
            <div class="page-sub">把工具库里的工具编排成可复用的子代理工作流，在对话中按需调用</div>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <span class="s-icon">🔍</span>
              <input
                v-model="keyword"
                placeholder="搜索技能名称或描述…"
                @input="onSearchInput"
              />
            </div>
            <button class="btn btn-primary btn-add" @click="openCreate">＋ 新建技能</button>
          </div>
        </div>
      </div>

      <!-- 内容区 -->
      <div class="content">
        <div v-if="loading" class="state-block">加载中…</div>
        <div v-else-if="error" class="state-block error">
          <p>{{ error }}</p>
          <button class="btn btn-ghost" @click="load">重试</button>
        </div>
        <div v-else-if="!list.items.length" class="state-block">
          <div class="empty-icon">✦</div>
          <template v-if="isSkillEmpty">
            <p>还没有技能</p>
            <span class="empty-hint">把工具库里的工具编排成一条工作流，就是第一个技能</span>
            <button class="btn btn-primary empty-cta" @click="openCreate">＋ 新建第一个技能</button>
          </template>
          <template v-else>
            <p>没有匹配的技能</p>
            <span class="empty-hint">试试换个关键词，或清空搜索查看全部技能</span>
          </template>
        </div>

        <template v-else>
          <div class="skill-list">
            <SkillRow
              v-for="s in list.items"
              :key="s.id"
              :skill="s"
              :tool-map="toolMap"
              @detail="openDetail"
              @edit="openEdit"
              @remove="askRemove"
              @toggle="onToggle"
            />
          </div>
        </template>
      </div>

      <!-- 底栏：无分页（技能数量天然少） -->
      <div v-if="list.items.length" class="list-footer">
        <span class="info">共 {{ list.total }} 个技能 · 已启用 {{ list.enabled_count }} 个</span>
      </div>
    </div>

    <!-- 新建/编辑（共用一个表单弹窗） -->
    <SkillFormModal
      :visible="formVisible"
      :skill="editing"
      :tools="tools"
      @close="formVisible = false"
      @saved="load"
    />

    <!-- 详情 -->
    <SkillDetailModal
      :visible="detailVisible"
      :skill-id="detailId"
      :tool-map="toolMap"
      @close="detailVisible = false"
      @try="tryInChat"
    />

    <!-- 删除确认：复用通用确认弹窗 -->
    <ConfirmDialog
      :visible="confirm.visible"
      :title="confirm.title"
      :message="confirm.message"
      :warning="confirm.warning"
      warning-tone="red"
      :confirm-text="confirm.confirmText"
      :busy="confirm.busy"
      @cancel="confirm.visible = false"
      @confirm="onConfirm"
    >
      <template #message>
        删除后对话中将无法再调用该子代理，历史运行记录与产出文件仍会保留。此操作无法恢复。
      </template>
    </ConfirmDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'
import { useConversationStore } from '@/stores/conversation'
import Sidebar from '@/components/Sidebar.vue'
import SkillRow from '@/components/skill/SkillRow.vue'
import SkillFormModal from '@/components/skill/SkillFormModal.vue'
import SkillDetailModal from '@/components/skill/SkillDetailModal.vue'
import ConfirmDialog from '@/components/tools/ConfirmDialog.vue'
import { isApiNotFound } from '@/api/client'
import { deleteSkill, fetchSkills, setSkillEnabled, type Skill, type SkillListResponse } from '@/api/skill'
import { fetchTools, type Tool } from '@/api/tools'

const router = useRouter()
const auth = useAuthStore()
const session = useSessionStore()
const chat = useChatStore()
const conversation = useConversationStore()

const EMPTY_LIST: SkillListResponse = { items: [], total: 0, enabled_count: 0 }

const list = ref<SkillListResponse>(EMPTY_LIST)
/** 启用中的工具（步骤下拉 + 工具名兜底展示用） */
const tools = ref<Tool[]>([])
const toolMap = computed(() => new Map(tools.value.map((t) => [t.id, t])))

const keyword = ref('')
const loading = ref(false)
const error = ref('')

/** 无搜索词且总数为 0 → 整库为空（区别于「搜索无结果」） */
const isSkillEmpty = computed(() => !keyword.value.trim() && list.value.total === 0)

// ─── 数据加载 ────────────────────────────────────────
/**
 * 拉取技能列表 + 启用中的工具。
 * - 技能列表 404（后端暂无 /api/skills）→ 降级为空列表，显示「还没有技能」
 * - 工具列表失败不阻塞页面（弹窗里会给出「先到工具库启用工具」的提示）
 */
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [skillsResp, toolsResp] = await Promise.all([
      fetchSkills({ keyword: keyword.value.trim() || undefined }).catch((e) => {
        if (isApiNotFound(e)) return null
        throw e
      }),
      // 后端 MAX_PAGE_SIZE = 100（tools.py），超出会 400 → 步骤下拉会空，故取上限
      fetchTools({ status: 'enabled', page: 1, page_size: 100 }).catch(() => null),
    ])
    list.value = skillsResp ?? EMPTY_LIST
    tools.value = toolsResp?.items ?? []
  } catch (e) {
    error.value = `技能列表加载失败：${(e as Error).message}`
  } finally {
    loading.value = false
  }
}

// 搜索 300ms 防抖（与其它管理页一致）
let searchTimer: ReturnType<typeof setTimeout> | undefined
function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 300)
}

// ─── 新建 / 编辑 ─────────────────────────────────────
const formVisible = ref(false)
const editing = ref<Skill | null>(null)

/** 新建：必须清掉上一次编辑的对象，否则表单会以「编辑」状态打开 */
function openCreate() {
  editing.value = null
  formVisible.value = true
}

function openEdit(skill: Skill) {
  editing.value = skill
  formVisible.value = true
}

// ─── 详情 ────────────────────────────────────────────
const detailVisible = ref(false)
const detailId = ref<number | null>(null)

function openDetail(skill: Skill) {
  detailId.value = skill.id
  detailVisible.value = true
}

// ─── 启停（乐观更新，失败回滚）────────────────────────
async function onToggle(skill: Skill) {
  const next = !skill.enabled
  const prev = skill.enabled
  skill.enabled = next // 乐观
  try {
    await setSkillEnabled(skill.id, next)
    list.value.enabled_count += next ? 1 : -1
  } catch (e) {
    skill.enabled = prev // 回滚
    alert(`启停失败：${(e as Error).message}`)
  }
}

// ─── 删除确认 ────────────────────────────────────────
const confirm = reactive({
  visible: false,
  title: '',
  message: '',
  warning: '',
  confirmText: '确认删除',
  busy: false,
  target: null as Skill | null,
})

function askRemove(skill: Skill) {
  confirm.visible = true
  confirm.target = skill
  confirm.busy = false
  confirm.title = `删除技能「${skill.name}」？`
  // 与设计稿 04 一致：红色风险条，运行次数加粗 + 建议停用
  confirm.warning = skill.run_count
    ? `该技能已被运行 ${skill.run_count} 次；若只是暂时不用，建议停用而不是删除。`
    : '若只是暂时不用，建议停用而不是删除。'
}

async function onConfirm() {
  const skill = confirm.target
  if (!skill) return
  confirm.busy = true
  try {
    await deleteSkill(skill.id)
    confirm.visible = false
    await load()
  } catch (e) {
    alert(`删除失败：${(e as Error).message}`)
  } finally {
    confirm.busy = false
  }
}

// ─── 在对话中试用：跳回聊天页并预填调用话术 ────────────
const CHAT_DRAFT_KEY = 'qap_chat_draft'

function tryInChat(skill: Skill) {
  detailVisible.value = false
  sessionStorage.setItem(CHAT_DRAFT_KEY, `用「${skill.name}」`)
  router.push({ name: 'chat' })
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
.skills {
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
  padding: 18px 28px 16px;
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

.btn-primary {
  background: var(--orange);
  color: #fff;
}
.btn-primary:hover {
  background: var(--orange-hover);
}
.btn-add {
  padding: 9px 16px;
  font-size: 13px;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  font-weight: 600;
  font-family: inherit;
  transition: background 0.15s;
}
.btn-ghost {
  background: #f5f5f4;
  color: var(--text);
  border: none;
  border-radius: 10px;
  padding: 9px 18px;
  font-size: 13px;
  cursor: pointer;
  font-weight: 600;
  font-family: inherit;
}
.btn-ghost:hover {
  background: #e7e5e4;
}

.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.skill-list {
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

.list-footer {
  flex-shrink: 0;
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: 12px 28px;
  display: flex;
  align-items: center;
  font-size: 12.5px;
}
.list-footer .info {
  color: var(--text-secondary);
}
</style>
