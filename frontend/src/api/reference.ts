import api from './client'
import type { ReferenceImage } from '../types'

export const referenceApi = {
  list: (isGlobal?: boolean) => api.get<ReferenceImage[]>('/references', { params: { is_global: isGlobal } }),
  get: (id: string) => api.get<ReferenceImage>(`/references/${id}`),
  upload: (file: File, name?: string, isGlobal?: boolean, strength?: number) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post<ReferenceImage>('/references/upload', formData, {
      params: { name: name || file.name, is_global: isGlobal || false, strength: strength || 0.5 },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  update: (id: string, data: { name?: string; is_global?: boolean; strength?: number; crop_config?: Record<string, unknown> }) =>
    api.put<ReferenceImage>(`/references/${id}`, data),
  delete: (id: string) => api.delete(`/references/${id}`),
}
