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

// ─── 分子结构附件（用户在「⌬ 结构」里输入的）───
export interface StructurePayload {
  /** 'xyz' = 直接粘贴坐标；'file' = 上传文件后本地读出文本；'smiles' = 前端已禁用，仅保留兼容 */
  format: 'xyz' | 'file' | 'smiles'
  data: string
  filename?: string
}

/** 后端 attachment_done 事件回传的元数据 */
export interface AttachmentMeta {
  filename: string
  format: string
  natoms?: number
  formula?: string
  /** 相对 backend 工作目录的路径，便于用户后续引用 */
  path?: string
}

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
  // 用户消息上的附件标记。挂在**用户**消息上，不是助手消息 ——
  // 渲染分支见 Message.vue 的 user 分支（那里只认 text，不处理会静默消失）。
  | {
      type: 'attachment'
      filename: string
      format: string
      status: 'pending' | 'ok' | 'failed'
      natoms?: number
      formula?: string
      path?: string
    }

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
  // 附件已解析、校验并落盘。之后执行用的 input_file 就是它的 path。
  | { event: 'attachment_done'; data: AttachmentMeta }
  | { event: 'result_viz'; data: VizResult }
  // 会话已就绪（planning 之前发出）。conversation_id 可能与请求里带的不一样 ——
  // 客户端传了一个不存在、或属于别人的 id 时，后端会换一个新的（见方案 §3.1 B4）
  | { event: 'conversation_ready'; data: { conversation_id: string } }
  | {
      event: 'done'
      data: {
        status: string
        /** @deprecated 与 conversation_id 同值，仅为兼容保留；新代码用 conversation_id */
        session_id?: string
        conversation_id?: string
        message_count?: number
      }
    }
  // code 目前只有附件失败会带（ATTACHMENT_*），其余错误路径不填
  | { event: 'error'; data: { message: string; code?: string; conversation_id?: string } }

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
