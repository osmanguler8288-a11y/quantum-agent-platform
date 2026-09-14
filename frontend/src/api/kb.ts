/**
 * 知识库 API 层（真实接口）。
 *
 * 契约见 doc/design/README.md §8.4：
 * GET/POST /api/kb/documents、GET/PUT/DELETE /api/kb/documents/{id}、
 * PATCH /api/kb/documents/{id}/searchable、POST /api/kb/documents/{id}/reindex、
 * POST /api/kb/reindex、GET /api/kb/categories、GET /api/kb/stats。
 */
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from './client'

// ─── 类型 ────────────────────────────────────────────
export type DocIndexStatus = 'indexed' | 'indexing' | 'failed'
export type ChunkStrategy = 'paragraph' | 'fixed' | 'row'

export const CHUNK_STRATEGY_LABELS: Record<ChunkStrategy, string> = {
  paragraph: '按段落',
  fixed: '固定长度',
  row: '表格行',
}

export const CATEGORY_BADGE: Record<string, string> = {
  '文献': 'lit',
  '笔记': 'note',
  '数据': 'data',
  '报告 / SOP': 'sop',
}

/** 分类 → 图标样式类 + emoji（与设计稿一致） */
export const CATEGORY_ICON: Record<string, { cls: string; emoji: string }> = {
  '文献': { cls: 'pdf', emoji: '📄' },
  '笔记': { cls: 'md', emoji: '📝' },
  '数据': { cls: 'data', emoji: '📊' },
  '报告 / SOP': { cls: 'sop', emoji: '📖' },
}

export const CATEGORY_NAMES = ['文献', '笔记', '数据', '报告 / SOP']

export interface KbDoc {
  id: number
  name: string
  category: string
  index_status: DocIndexStatus
  /** 0–99，仅 index_status === 'indexing' 时非空 */
  index_progress: number | null
  /** 索引预计剩余秒数，仅 indexing 时非空 */
  index_remaining_sec: number | null
  /** index_status === 'failed' 时的失败原因 */
  index_error: string | null
  chunk_count: number | null
  char_count: number | null
  size_bytes: number
  tags: string[]
  description: string
  searchable: boolean
  citations_30d: number
  uploaded_by: string
  created_at: string
  updated_at: string
  strategy: ChunkStrategy
  chunk_limit: number
  // 详情接口才有
  index_model?: string
  last_indexed_at?: string | null
  chunk_preview?: { idx: number; text: string }[]
}

export interface KbListResponse {
  items: KbDoc[]
  total: number
  page: number
  page_size: number
}

export interface KbCategory {
  name: string
  count: number
}

export interface KbStats {
  documents: number
  chunks: number
  size_bytes: number
}

export interface KbListParams {
  keyword?: string
  category?: string
  index_status?: DocIndexStatus | 'all'
  page?: number
  page_size?: number
}

/** 上传的文件描述（前端 File 对象的轻量投影） */
export interface KbUploadFile {
  name: string
  size: number
}

export interface UploadPayload {
  files: KbUploadFile[]
  category: string
  tags: string[]
  description: string
  strategy: ChunkStrategy
  chunk_limit: number
  /** 索引完成后是否立即可被检索 */
  searchable: boolean
}

export interface DocUpdatePayload {
  name?: string
  category?: string
  tags?: string[]
  description?: string
  searchable?: boolean
}

// ─── 接口 ────────────────────────────────────────────
export async function fetchKbDocs(params: KbListParams = {}): Promise<KbListResponse> {
  const q = new URLSearchParams()
  if (params.keyword) q.set('keyword', params.keyword)
  if (params.category) q.set('category', params.category)
  if (params.index_status && params.index_status !== 'all') q.set('index_status', params.index_status)
  if (params.page) q.set('page', String(params.page))
  if (params.page_size) q.set('page_size', String(params.page_size))
  const qs = q.toString()
  return apiGet<KbListResponse>(`/api/kb/documents${qs ? '?' + qs : ''}`)
}

export async function fetchKbDoc(id: number, withPreview = true): Promise<KbDoc> {
  return apiGet<KbDoc>(`/api/kb/documents/${id}${withPreview ? '?preview=3' : ''}`)
}

export async function fetchKbCategories(): Promise<{ items: KbCategory[] }> {
  return apiGet<{ items: KbCategory[] }>('/api/kb/categories')
}

export async function fetchKbStats(): Promise<KbStats> {
  return apiGet<KbStats>('/api/kb/stats')
}

export async function uploadKbDocs(payload: UploadPayload): Promise<{ items: KbDoc[]; task_id: string }> {
  // 真实后端为 multipart 上传；等接口定型后再补 FormData 序列化
  return apiPost<{ items: KbDoc[]; task_id: string }>('/api/kb/documents', payload)
}

export async function updateKbDoc(id: number, payload: DocUpdatePayload): Promise<KbDoc> {
  return apiPut<KbDoc>(`/api/kb/documents/${id}`, payload)
}

export async function setKbDocSearchable(id: number, searchable: boolean) {
  return apiPatch<{ id: number; name: string; searchable: boolean }>(
    `/api/kb/documents/${id}/searchable`,
    { searchable },
  )
}

export async function reindexKbDoc(id: number) {
  return apiPost<{ id: number; name: string; index_status: string }>(`/api/kb/documents/${id}/reindex`, {})
}

export async function reindexKbAll() {
  return apiPost<{ queued: number }>('/api/kb/reindex', {})
}

export async function deleteKbDoc(id: number) {
  return apiDelete<{
    id: number
    name: string
    chunk_count: number
    restorable_until: string
  }>(`/api/kb/documents/${id}`)
}

// ─── 展示辅助 ────────────────────────────────────────
export function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes)) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

/** 486K 之类的紧凑字符数展示（详情弹窗统计卡用） */
export function formatChars(n: number | null): string {
  if (n === null || n === undefined) return '—'
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${Math.round(n / 1000)}K`
  return `${(n / 1_000_000).toFixed(1)}M`
}

export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function formatFullDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
