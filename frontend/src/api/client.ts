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
  // ⚠️ X-User-ID 是后端识别用户的来源（工具库用它做审计日志的 operator）。
  //    生产环境由 Go 网关校验 JWT 后注入，这里在前端补上是为了联调期能区分用户。
  //    它是**可伪造的** —— 当前后端不做鉴权，仅用于留痕。
  if (auth.user?.username) {
    headers['X-User-ID'] = auth.user.username
  }
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
    const message = data?.error || data?.detail || `请求失败 (${resp.status})`
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
