import api from './client'
import type { Rule } from '../types'

export const ruleApi = {
  list: (ruleType?: string) => api.get<Rule[]>('/rules', { params: { rule_type: ruleType } }),
  get: (id: string) => api.get<Rule>(`/rules/${id}`),
  create: (data: Partial<Rule>) => api.post<Rule>('/rules', data),
  update: (id: string, data: Partial<Rule>) => api.put<Rule>(`/rules/${id}`, data),
  delete: (id: string) => api.delete(`/rules/${id}`),
  toggle: (id: string) => api.put<Rule>(`/rules/${id}/toggle`),
}
