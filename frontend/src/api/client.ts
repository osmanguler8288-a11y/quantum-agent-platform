import { useAuthStore } from '@/stores/auth'

// 是否使用 mock（默认 true，联调时设 VITE_USE_MOCK=false）
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'

function authHeaders(headers: Record<string, string> = {}): Record<string, string> {
  const auth = useAuthStore()
  if (auth.token) {
    headers['Authorization'] = 'Bearer ' + auth.token
  }
  return headers
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
    throw new Error(message)
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
