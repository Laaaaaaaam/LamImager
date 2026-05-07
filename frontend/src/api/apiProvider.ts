import api from './client'
import type { ApiProvider, ApiProviderCreate, ApiProviderUpdate } from '../types'

export const providerApi = {
  list: (providerType?: string) =>
    api.get<ApiProvider[]>('/providers', { params: { provider_type: providerType } }),

  get: (id: string) =>
    api.get<ApiProvider>(`/providers/${id}`),

  create: (data: ApiProviderCreate) =>
    api.post<ApiProvider>('/providers', data),

  update: (id: string, data: ApiProviderUpdate) =>
    api.put<ApiProvider>(`/providers/${id}`, data),

  delete: (id: string) =>
    api.delete(`/providers/${id}`),

  test: (id: string) =>
    api.post(`/providers/${id}/test`),
}
