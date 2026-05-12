import api from './client'
import type { SessionInfo, Message, GenerateRequest } from '../types'

export const sessionApi = {
  list: () => api.get<SessionInfo[]>('/sessions'),

  get: (id: string) => api.get<SessionInfo>(`/sessions/${id}`),

  create: (title: string = '新会话') => api.post<SessionInfo>('/sessions', { title }),

  update: (id: string, data: { title?: string }) => api.put<SessionInfo>(`/sessions/${id}`, data),

  delete: (id: string) => api.delete(`/sessions/${id}`),

  getMessages: (id: string) => api.get<Message[]>(`/sessions/${id}/messages`),

  addMessage: (id: string, data: { content: string; message_type?: string; metadata?: Record<string, unknown> }) =>
    api.post<Message>(`/sessions/${id}/messages`, data),

  generate: (data: GenerateRequest) => api.post(`/sessions/${data.session_id}/generate`, data),

  executePlan: (sessionId: string, data: {
    strategy: string
    steps: { prompt: string; negative_prompt?: string; description?: string; image_count?: number; image_size?: string }[]
    reference_images?: string[]
    reference_labels?: Record<string, unknown>[]
    context_messages?: Record<string, unknown>[]
    negative_prompt?: string
    image_size?: string
  }) => api.post(`/sessions/${sessionId}/execute-plan`, data),

  cancel: (id: string) => api.post(`/sessions/${id}/cancel`),

  checkpoint: (id: string, approved: boolean, feedback: string = '') =>
    api.post(`/sessions/${id}/agent/checkpoint`, { approved, feedback }),
}
