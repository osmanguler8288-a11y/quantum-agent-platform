import { ApiError, authHeaders } from './client'

export interface DescriptorJob {
  id: string
  created_at: string
  status: string
  uploads: Record<string, { filename: string; size: number }>
  error?: string
  partial?: boolean
  failed_methods?: string[]
  result?: {
    descriptors?: Record<string, unknown>
    methods?: Record<string, { status: string; error?: string; reason?: string }>
    units?: Record<string, string>
  }
}

export class DescriptorApiError extends ApiError {
  constructor(message: string, status: number, public job?: DescriptorJob) {
    super(message, status)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch('/api/descriptors' + path, { ...init, headers: authHeaders() })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new DescriptorApiError(
      typeof data?.error === 'string' ? data.error : `描述符请求失败 (${response.status})`,
      response.status, data?.job,
    )
  }
  return data as T
}

export const listDescriptorJobs = () => request<{ items: DescriptorJob[] }>('')
export const getDescriptorJob = (id: string) => request<DescriptorJob>('/' + encodeURIComponent(id))

export function submitDescriptorJob(fchk: File, out: File | undefined, ti: number, oxygen: string, basic: boolean) {
  const body = new FormData()
  body.append('fchk', fchk)
  if (out) body.append('out', out)
  body.append('ti_index', String(ti))
  body.append('o_indices', oxygen.replace(/\s/g, ''))
  body.append('methods', basic ? 'basic' : 'hirshfeld,cm5,chelpg,mayer')
  // Let the browser set the multipart boundary; never automatically retry a POST.
  return request<DescriptorJob>('', { method: 'POST', body })
}

export async function downloadDescriptorFile(id: string, path: string, filename: string) {
  const response = await fetch(`/api/descriptors/${encodeURIComponent(id)}/${path}`, { headers: authHeaders() })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.error === 'string' ? body.error : `文件下载失败 (${response.status})`)
  }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
