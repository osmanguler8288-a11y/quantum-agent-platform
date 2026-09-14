/**
 * 对话管理 API 层（真实接口）。
 *
 * 契约见 doc/design/README.md §9.4：
 * GET    /api/conversations?keyword=&tab=&page=&page_size=
 * GET    /api/conversations/{id}
 * POST   /api/conversations
 * PUT    /api/conversations/{id}
 * PATCH  /api/conversations/{id}/flags
 * DELETE /api/conversations/{id}
 */
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from './client'

// ─── 类型 ────────────────────────────────────────────
/** 状态三态：进行中 / 已完成 / 已归档（与设计稿 9.2 一致） */
export type ConvStatus = 'active' | 'completed' | 'archived'

/** Tab 分组：全部 / 进行中 / 已归档 */
export type ConvTab = 'all' | 'active' | 'archived'

export interface ConvSummary {
  id: number
  title: string
  status: ConvStatus
  model: string
  tags: string[]
  /** 首条消息摘要（列表行展示用） */
  snippet: string
  message_count: number
  pinned: boolean
  archived: boolean
  created_at: string
  updated_at: string
}

export interface ConvMessage {
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

/** 详情接口在列表字段之上补充的只读信息 */
export interface ConvDetail extends ConvSummary {
  system_prompt: string | null
  tool_calls: number
  total_tokens: number
  /** 累计费用（美元） */
  total_cost: number
  first_message: ConvMessage | null
  last_reply: ConvMessage | null
}

export interface ConvTabCounts {
  all: number
  active: number
  archived: number
}

export interface ConvListResponse {
  items: ConvSummary[]
  total: number
  page: number
  page_size: number
  /** 各 Tab 的总数；后端未提供时前端会用轻量请求自行补齐 */
  counts?: ConvTabCounts
}

export interface ConvListParams {
  keyword?: string
  tab?: ConvTab
  page?: number
  page_size?: number
}

export interface ConvCreatePayload {
  model: string
  title?: string
  system_prompt?: string
}

export interface ConvUpdatePayload {
  title?: string
  tags?: string[]
}

export interface ConvFlagsPayload {
  pinned?: boolean
  archived?: boolean
}

// ─── 新建对话的可选模型（设计稿 02 固定列表，联调后可改为接口下发） ───
export const MODEL_OPTIONS = [
  { id: 'gpt-4o', name: 'GPT-4o', mark: 'G', meta: '综合能力强' },
  { id: 'claude-sonnet-4', name: 'Claude Sonnet 4', mark: 'C', meta: '长文档 / 推理' },
  { id: 'deepseek-v3', name: 'DeepSeek-V3', mark: 'D', meta: '高性价比' },
  { id: 'qwen2.5-72b', name: 'Qwen2.5-72B', mark: 'Q', meta: '本地部署' },
] as const

/** 模型 id → 展示名（列表/详情徽章用，未知模型原样返回 id） */
export function modelLabel(id: string): string {
  return MODEL_OPTIONS.find((m) => m.id === id)?.name ?? id
}

// ─── 接口 ────────────────────────────────────────────
export async function fetchConversations(params: ConvListParams = {}): Promise<ConvListResponse> {
  const q = new URLSearchParams()
  if (params.keyword) q.set('keyword', params.keyword)
  if (params.tab && params.tab !== 'all') q.set('tab', params.tab)
  if (params.page) q.set('page', String(params.page))
  if (params.page_size) q.set('page_size', String(params.page_size))
  const qs = q.toString()
  return apiGet<ConvListResponse>(`/api/conversations${qs ? '?' + qs : ''}`)
}

export async function fetchConversation(id: number): Promise<ConvDetail> {
  return apiGet<ConvDetail>(`/api/conversations/${id}`)
}

export async function createConversation(payload: ConvCreatePayload): Promise<ConvDetail> {
  return apiPost<ConvDetail>('/api/conversations', payload)
}

export async function updateConversation(id: number, payload: ConvUpdatePayload): Promise<ConvSummary> {
  return apiPut<ConvSummary>(`/api/conversations/${id}`, payload)
}

export async function setConversationFlags(id: number, flags: ConvFlagsPayload): Promise<ConvSummary> {
  return apiPatch<ConvSummary>(`/api/conversations/${id}/flags`, flags)
}

export async function deleteConversation(id: number): Promise<{ id: number }> {
  return apiDelete<{ id: number }>(`/api/conversations/${id}`)
}

// ─── 展示辅助 ────────────────────────────────────────
/**
 * 相对时间（与设计稿 01 的文案粒度一致）：
 * 刚刚 / N 分钟前 / N 小时前 / 昨天 HH:MM / N 天前 / 上周 / N 周前 / 超过一个月给完整日期
 */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const min = Math.floor(diffMs / 60_000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24 && d.getDate() === now.getDate()) return `${hour} 小时前`
  const day = Math.floor(diffMs / 86_400_000)
  const pad = (n: number) => String(n).padStart(2, '0')
  if (day === 1) return `昨天 ${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (day < 7) return `${day} 天前`
  if (day < 14) return '上周'
  if (day < 30) return `${Math.floor(day / 7)} 周前`
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** 累计费用：$0.68 / $12.40（不足 1 分钱显示 $0.01，避免一串零） */
export function formatCost(usd: number): string {
  if (!Number.isFinite(usd) || usd <= 0) return '$0.00'
  return `$${usd < 0.01 ? 0.01 : usd.toFixed(2)}`
}
