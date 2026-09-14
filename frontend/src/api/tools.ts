/**
 * 工具库 API 层。
 *
 * 契约见 doc/backdesign/工具库后端设计.md §4。
 * 后端错误统一是 { error: string, code: string, detail?: any } —— client.ts 的
 * request() 会把 error 抛成 Error.message，所以调用方 catch 到的就是可读文案。
 */
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from './client'

// ─── 类型 ────────────────────────────────────────────
export type ToolSource = 'builtin' | 'mcp'
export type ToolStatus = 'enabled' | 'disabled'

export interface ToolCapabilities {
  can_edit: boolean
  can_delete: boolean
  can_disable: boolean
  can_restore: boolean
  /** 非空时前端应把它作为删除按钮的禁用原因 tooltip */
  delete_blocked_reason: string | null
  /** 内置工具的契约字段不可改 */
  builtin_fields_immutable: boolean
}

export interface ParamRow {
  name: string
  type: string
  required: boolean
  description: string
}

export interface ToolStats {
  total_invocations: number
  /** ⚠️ 无调用记录时为 null（不是 0，更不是 NaN）—— 展示成「—」 */
  success_rate: number | null
  avg_duration_ms: number | null
  last_invoked_at: string | null
  recent_30d_invocations: number
}

export interface Invocation {
  id: number
  tool_name?: string
  task_title: string | null
  status: 'success' | 'error'
  duration_ms: number | null
  started_at: string
  error_code: string | null
  error_message?: string | null
  session_id?: string | null
  step_index?: number | null
}

export interface Tool {
  id: number
  name: string
  display_name: string
  icon: string
  category_id: number
  category: string
  source: ToolSource
  status: ToolStatus
  endpoint: string | null
  user_description: string
  llm_description?: string
  tags: string[]
  is_destructive: boolean
  invocation_count: number
  last_invoked_at: string | null
  created_at: string
  updated_at: string
  deleted: boolean
  deleted_at: string | null
  capabilities: ToolCapabilities
  // 详情接口才有
  parameters?: Record<string, any>
  param_template?: Record<string, any>
  param_rows?: ParamRow[]
  stats?: ToolStats
  recent_invocations?: Invocation[]
}

export interface ToolListResponse {
  items: Tool[]
  total: number
  page: number
  page_size: number
  enabled_count: number
}

export interface Category {
  id: number
  name: string
  count: number
  is_builtin: boolean
}

export interface CategoryListResponse {
  items: Category[]
  total: number
}

export interface ToolPayload {
  name?: string
  display_name: string
  category_id: number
  user_description: string
  source?: ToolSource
  endpoint?: string | null
  icon?: string
  tags?: string[]
  parameters?: Record<string, any>
  param_template?: Record<string, any>
  status?: ToolStatus
}

export interface ListParams {
  keyword?: string
  category?: string
  status?: 'all' | 'enabled' | 'disabled'
  page?: number
  page_size?: number
  include_deleted?: boolean
}

// ─── 接口 ────────────────────────────────────────────
export function fetchTools(params: ListParams = {}) {
  const q = new URLSearchParams()
  if (params.keyword) q.set('keyword', params.keyword)
  if (params.category) q.set('category', params.category)
  if (params.status && params.status !== 'all') q.set('status', params.status)
  if (params.page) q.set('page', String(params.page))
  if (params.page_size) q.set('page_size', String(params.page_size))
  if (params.include_deleted) q.set('include_deleted', 'true')
  const qs = q.toString()
  return apiGet<ToolListResponse>(`/api/tools${qs ? '?' + qs : ''}`)
}

export function fetchCategories() {
  return apiGet<CategoryListResponse>('/api/tools/categories')
}

export function fetchTool(id: number, withStats = true, invocationLimit = 5) {
  return apiGet<Tool>(
    `/api/tools/${id}?with_stats=${withStats}&invocation_limit=${invocationLimit}`,
  )
}

export function createTool(payload: ToolPayload) {
  return apiPost<Tool>('/api/tools', payload)
}

export function updateTool(id: number, payload: Partial<ToolPayload>) {
  return apiPut<Tool>(`/api/tools/${id}`, payload)
}

export function setToolStatus(id: number, status: ToolStatus) {
  return apiPatch<{
    id: number
    name: string
    status: ToolStatus
    changed: boolean
    /** false 表示启停没有真正作用到 Agent（registry 重建失败）*/
    registry_reloaded: boolean
    warning?: string
  }>(`/api/tools/${id}/status`, { status })
}

export function deleteTool(id: number) {
  return apiDelete<{
    id: number
    name: string
    deleted_at: string
    restorable_until: string
    recent_30d_invocations: number
  }>(`/api/tools/${id}`)
}

export function restoreTool(id: number) {
  return apiPost<{ id: number; name: string; status: ToolStatus }>(
    `/api/tools/${id}/restore`,
    {},
  )
}

export function fetchInvocations(id: number, page = 1, pageSize = 20, status = 'all') {
  const q = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    status,
  })
  return apiGet<{ items: Invocation[]; total: number; page: number; page_size: number }>(
    `/api/tools/${id}/invocations?${q.toString()}`,
  )
}

// ─── 展示辅助 ────────────────────────────────────────
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rest = Math.round(s % 60)
  return `${m}m ${rest}s`
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** 成功率：null → 「—」（后端约定无数据时返回 null，避免 NaN） */
export function formatRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '—'
  return `${(rate * 100).toFixed(1)}%`
}

export function formatCount(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString('zh-CN')
}
