import type { SSEEvent } from '@/types'
import { authHeaders } from './client'

/**
 * 以 POST + fetch + ReadableStream 方式消费 SSE 流。
 * 后端接口是 POST /api/workflow/stream，不能用 EventSource（EventSource 只支持 GET）。
 *
 * ⚠️ 这里不能用 client.ts 的 request()（它调 resp.json()，会把流读干），
 *    但**请求头必须走同一个 authHeaders()** —— 否则会漏掉 X-User-ID，
 *    后端识别不出用户，对话链路与工具调用埋点都会记成 default_user。
 */
export async function streamWorkflow(
  body: { input_data: { user_query: string; structure?: unknown }; session_id: string | null },
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const resp = await fetch('/api/workflow/stream', {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
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
