import type { SSEEvent } from '@/types'
import { useAuthStore } from '@/stores/auth'

/**
 * 以 POST + fetch + ReadableStream 方式消费 SSE 流。
 * 后端接口是 POST /api/workflow/stream，不能用 EventSource（EventSource 只支持 GET）。
 */
export async function streamWorkflow(
  body: { input_data: { user_query: string; structure?: unknown }; session_id: string | null },
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const auth = useAuthStore()

  const resp = await fetch('/api/workflow/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(auth.token ? { Authorization: 'Bearer ' + auth.token } : {}),
    },
    body: JSON.stringify(body),
  })

  if (!resp.ok) {
    let msg = `请求失败 (${resp.status})`
    try {
      const err = await resp.json()
      msg = err.error || err.detail || msg
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }

  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (!payload) continue
      try {
        onEvent(JSON.parse(payload) as SSEEvent)
      } catch {
        /* 忽略无法解析的块 */
      }
    }
  }
}
