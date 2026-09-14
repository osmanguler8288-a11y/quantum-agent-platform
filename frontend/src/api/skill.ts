/**
 * 技能中心 API 层（真实接口）。
 *
 * 契约见 doc/design/README.md §10.4：
 * GET    /api/skills?keyword=&page=&page_size=   # 列表；返回 items/total 与 enabled_count
 * GET    /api/skills/{id}                        # 详情（含 steps 与运行统计）
 * POST   /api/skills                             # 新建（name / description / steps[]）
 * PUT    /api/skills/{id}                        # 编辑（整体覆盖 name / description / steps[]）
 * PATCH  /api/skills/{id}/enabled                # 启停（{ enabled: bool }）
 * DELETE /api/skills/{id}                        # 删除（软删除）
 */
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from './client'

// ─── 类型 ────────────────────────────────────────────
export type SkillToolSource = 'builtin' | 'mcp'

/** 工作流一步：用哪个工具 + 给这一步的自然语言说明（note 可选） */
export interface SkillStep {
  tool_id: number
  /** 列表/详情接口回填的工具展示信息（新建/编辑提交时不需要带） */
  tool_name?: string
  icon?: string
  source?: SkillToolSource
  note?: string
}

export interface Skill {
  id: number
  name: string
  description: string
  /** 有序步骤链：前一步的输出即后一步的输入 */
  steps: SkillStep[]
  enabled: boolean
  run_count: number
  /** 0–1 小数；无运行记录时为 null */
  success_rate: number | null
  /** 平均耗时（秒）；无运行记录时为 null */
  avg_duration_sec: number | null
  last_run_at: string | null
  created_at: string
  updated_at: string
}

export interface SkillListResponse {
  items: Skill[]
  total: number
  enabled_count: number
}

export interface SkillListParams {
  keyword?: string
}

export interface SkillPayload {
  name: string
  description: string
  steps: { tool_id: number; note?: string }[]
}

// ─── 接口 ────────────────────────────────────────────
export function fetchSkills(params: SkillListParams = {}): Promise<SkillListResponse> {
  const q = new URLSearchParams()
  if (params.keyword) q.set('keyword', params.keyword)
  const qs = q.toString()
  return apiGet<SkillListResponse>(`/api/skills${qs ? '?' + qs : ''}`)
}

export function fetchSkill(id: number): Promise<Skill> {
  return apiGet<Skill>(`/api/skills/${id}`)
}

export function createSkill(payload: SkillPayload): Promise<Skill> {
  return apiPost<Skill>('/api/skills', payload)
}

export function updateSkill(id: number, payload: SkillPayload): Promise<Skill> {
  return apiPut<Skill>(`/api/skills/${id}`, payload)
}

export function setSkillEnabled(id: number, enabled: boolean): Promise<Skill> {
  return apiPatch<Skill>(`/api/skills/${id}/enabled`, { enabled })
}

export function deleteSkill(id: number): Promise<{ id: number }> {
  return apiDelete<{ id: number }>(`/api/skills/${id}`)
}

// ─── 展示辅助 ────────────────────────────────────────
/** 平均耗时：秒 → 「42 秒 / 14 分钟 / 1 小时 22 分」；无数据 → 「—」 */
export function formatSkillDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || !Number.isFinite(sec)) return '—'
  if (sec < 60) return `${Math.round(sec)} 秒`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟`
  const h = Math.floor(min / 60)
  const rest = min % 60
  return rest ? `${h} 小时 ${rest} 分` : `${h} 小时`
}

/** 成功率：0–1 小数 → 「98%」；无运行记录 → 「—」 */
export function formatSkillRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) return '—'
  return `${Math.round(rate * 100)}%`
}

/**
 * 工具链节点展示名：优先用接口回填的 tool_name，
 * 否则查前端已加载的工具表，最后兜底「工具 #id」。
 */
export function stepToolName(
  step: SkillStep,
  toolMap: Map<number, { display_name: string }>,
): string {
  if (step.tool_name) return step.tool_name
  return toolMap.get(step.tool_id)?.display_name ?? `工具 #${step.tool_id}`
}

/** 步骤来源徽章文案（详情弹窗用） */
export function stepSourceLabel(step: SkillStep): string {
  return step.source === 'mcp' ? 'MCP' : step.source === 'builtin' ? '内置' : ''
}
