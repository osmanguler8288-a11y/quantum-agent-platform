// ─── 计划步骤 ───
export interface PlanStep {
  type: 'tool' | 'reasoning'
  step: string // 工具名或分析名
  action?: string // 操作描述
  params?: Record<string, unknown>
}

// ─── 工具结果 ───
export interface ToolResult {
  status: 'success' | 'error'
  tool?: string
  result?: string
  message?: string
}

// ─── 评审结论 ───
export interface Verdict {
  passed: boolean
  reason?: string
  suggestions?: string
  comment?: string
}

// ─── 步骤执行状态 ───
export interface StepStatus {
  index: number
  step?: PlanStep
  status: 'running' | 'done' | 'fail'
  result?: ToolResult
}

// ─── 可视化结果（按 type 分发）───
export interface Orbital {
  idx: number
  energy_eV: number
  occ: boolean
}

export interface Transition {
  from: number
  to: number
  weight: number
}

export interface ExcitedState {
  n: number
  energy_eV: number
  wavelength_nm: number
  osc_strength: number
  transitions?: Transition[]
}

export interface Atom {
  symbol: string
  x: number
  y: number
  z: number
}

export type VizResult =
  | { type: 'homo_lumo'; homo_e: number; lumo_e: number; gap_eV: number; orbitals: Orbital[] }
  | { type: 'dipole'; components: { x: number; y: number; z: number; tot: number } }
  | { type: 'tddft'; states: ExcitedState[] }
  | { type: 'freq'; n_imag: number; freqs: number[]; intensities: number[]; thermo?: Record<string, string> }
  | { type: 'structure'; atoms: Atom[] }
  | { type: 'energy'; label: string; value: number; unit: string }

// ─── 消息块（一条助手消息由多个块组成）───
export type MessageBlock =
  | { type: 'text'; text: string }
  | { type: 'thinking'; text: string }
  | { type: 'plan'; plan: PlanStep[] }
  | { type: 'steps'; steps: StepStatus[] }
  | { type: 'verdict'; verdict: Verdict }
  | { type: 'retry'; retryCount: number }
  | { type: 'viz'; viz: VizResult }
  | { type: 'error'; message: string }
  | { type: 'done'; status: string }

// ─── 消息 ───
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  blocks: MessageBlock[]
}

// ─── SSE 事件 ───
export type SSEEvent =
  | { event: 'thinking_chunk'; data: string }
  | { event: 'plan_done'; data: PlanStep[] }
  | { event: 'step_start'; data: { index: number; step: PlanStep } }
  | { event: 'step_done'; data: { index: number; result: ToolResult } }
  | { event: 'verdict_done'; data: Verdict }
  | { event: 'retry'; data: { retry_count: number } }
  | { event: 'memory_done'; data: { count: number } }
  | { event: 'rag_done'; data: { context_len: number } }
  | { event: 'result_viz'; data: VizResult }
  | { event: 'done'; data: { status: string; session_id?: string } }
  | { event: 'error'; data: { message: string } }

// ─── 记忆 ───
export type MemoryType = 'working' | 'episodic' | 'semantic' | 'perceptual'

export interface MemoryItem {
  id?: string
  type: MemoryType
  content: string
  importance: number
  timestamp?: string
}

// ─── 认证 ───
export interface User {
  id?: number
  username: string
  email?: string
}

export interface AuthResponse {
  token: string
  user: User
}

// ─── 会话 ───
export interface Conversation {
  id: string
  title: string
  updatedAt: string
}

// ─── 技能（预留 MCP 接入）───
export interface Skill {
  id: string
  name: string
  description: string
  category: string
  source: 'builtin' | 'mcp'
  status: 'available' | 'pending'
}
