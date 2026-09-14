import { useAuthStore } from '@/stores/auth'

// 是否使用 mock（默认 true，联调时设 VITE_USE_MOCK=false）
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'

/**
 * 构造带认证信息的请求头。
 *
 * ⚠️ 导出的目的是让**所有**发请求的地方都走这里，包括不能用 `request()` 的 SSE：
 *    sse.ts 需要自己 fetch + ReadableStream，此前它手写 headers，漏掉了 X-User-ID，
 *    导致对话链路的日志与工具调用埋点全部被记成 default_user。
 */
export function authHeaders(headers: Record<string, string> = {}): Record<string, string> {
  const auth = useAuthStore()
  if (auth.token) {
    headers['Authorization'] = 'Bearer ' + auth.token
  }
  // ⚠️ 这里**不发 X-User-ID**，尽管后端就是靠它识别用户的。
  //
  //    原因：网关注入的是 JWT 里的**数字 user_id**，而前端手上只有**用户名**。
  //    两个都塞进同一个 header，谁赢取决于有没有经过网关 —— 一旦两者混进同一张
  //    表（比如 conversation.user_id），就会出现「A 的会话归到 B 名下」。
  //    所以身份只保留一条路径：浏览器 → 网关 → 注入 X-User-ID → FastAPI。
  //
  //    代价：**FastAPI(:8001) 绝不能对外暴露**，直连时它拿不到任何身份信息，
  //    所有请求都会退化成 default_user。见 doc/对话落库-实施方案.md §3.1 B1/B2。
  return headers
}

/** 带 HTTP 状态码的 API 错误（catch 后可用 status 区分 404/500 等） */
export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 是否为 404（后端路由不存在 / 资源不存在）——调用方可据此降级为空状态 */
export function isApiNotFound(e: unknown): boolean {
  return e instanceof ApiError && e.status === 404
}

/**
 * 响应体为空时的兜底文案。
 *
 * ⚠️ 为什么需要：网关（Go）到 FastAPI 那一段断掉时，网关返回的是
 *    **content-length: 0 的空 502**，前端拿不到任何 error 字段，
 *    只能显示「请求失败 (502)」—— 完全看不出是后端没启动。
 *    这类"哪一跳断了"的信息必须在这里补上，否则每次都要重新排查一遍。
 */
const STATUS_HINT: Record<number, string> = {
  502: '后端服务不可达（FastAPI 没在运行）。执行 backend/start-dev.ps1 启动',
  503: '服务暂时不可用，请稍后重试',
  504: '后端响应超时',
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, {
    ...options,
    headers: authHeaders(options.headers as Record<string, string>),
  })

  let data: any = null
  try {
    data = await resp.json()
  } catch {
    /* 非 JSON 响应 */
  }

  if (!resp.ok) {
    // ⚠️ 只认**字符串**的 error/detail：FastAPI 默认的 422 里 detail 是数组，
    //    直接透传会让界面渲染出 "[object Object]"（或一长串 [object Object],...）。
    const raw = data?.error ?? data?.detail
    const message =
      (typeof raw === 'string' && raw) || STATUS_HINT[resp.status] || `请求失败 (${resp.status})`
    throw new ApiError(message, resp.status)
  }
  return data as T
}

export function apiPost<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function apiGet<T>(url: string): Promise<T> {
  return request<T>(url, { method: 'GET' })
}

export function apiPut<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function apiPatch<T>(url: string, body?: unknown): Promise<T> {
  return request<T>(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export function apiDelete<T>(url: string, body?: unknown): Promise<T> {
  return request<T>(url, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}
