import { request } from './client'
import type { JobResponse } from '../types'

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api'

export const jobsApi = {
  list: (status?: string, limit = 50) => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    params.set('limit', String(limit))
    return request<JobResponse[]>(`/jobs?${params}`)
  },
  get: (id: string) => request<JobResponse>(`/jobs/${id}`),
  cancel: (id: string) =>
    request<{ cancelled: boolean; job_id: string }>(`/jobs/${id}`, { method: 'DELETE' }),
}

/** Open an SSE connection to stream job logs. Returns a cleanup function. */
export function streamLogs(
  jobId: string,
  onLine: (line: string) => void,
  onDone: (status: string) => void,
): () => void {
  const url = `${BASE_URL}/jobs/${jobId}/logs`
  const es = new EventSource(url)
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.done) {
        onDone(data.status)
        es.close()
      } else if (data.line) {
        onLine(data.line)
      }
    } catch { /* ignore */ }
  }
  es.onerror = () => es.close()
  return () => es.close()
}
