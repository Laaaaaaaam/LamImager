import api from './client'
import type { Skill } from '../types'

export const skillApi = {
  list: () => api.get<Skill[]>('/skills'),
  get: (id: string) => api.get<Skill>(`/skills/${id}`),
  create: (data: Partial<Skill>) => api.post<Skill>('/skills', data),
  update: (id: string, data: Partial<Skill>) => api.put<Skill>(`/skills/${id}`, data),
  delete: (id: string) => api.delete(`/skills/${id}`),
  import: (data: { name: string; description?: string; prompt_template?: string; parameters?: Record<string, unknown> }) =>
    api.post<Skill>('/skills/import', data),
}
