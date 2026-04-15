import { request } from './client'
import type { FlowCreateRequest, FlowResponse, FlowUpdateRequest, JobResponse } from '../types'

export const flowsApi = {
  list: () => request<FlowResponse[]>('/flows'),
  get: (id: string) => request<FlowResponse>(`/flows/${id}`),
  create: (body: FlowCreateRequest) =>
    request<FlowResponse>('/flows', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, body: FlowUpdateRequest) =>
    request<FlowResponse>(`/flows/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (id: string) =>
    request<{ deleted: boolean; flow_id: string }>(`/flows/${id}`, { method: 'DELETE' }),
  run: (id: string) =>
    request<JobResponse>(`/flows/${id}/run`, { method: 'POST' }),
}
