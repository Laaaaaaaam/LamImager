import api from './client'
import type { PlanTemplate } from '../types'

export const planTemplateApi = {
  list: () => api.get<PlanTemplate[]>('/plan-templates'),

  get: (id: string) => api.get<PlanTemplate>(`/plan-templates/${id}`),

  create: (data: Partial<PlanTemplate>) => api.post<PlanTemplate>('/plan-templates', data),

  update: (id: string, data: Partial<PlanTemplate>) => api.put<PlanTemplate>(`/plan-templates/${id}`, data),

  delete: (id: string) => api.delete(`/plan-templates/${id}`),

  apply: (id: string, variables: Record<string, string>) =>
    api.post<{ steps: PlanTemplate['steps'] }>(`/plan-templates/${id}/apply`, { variables }),
}
