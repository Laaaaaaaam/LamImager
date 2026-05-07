import api from './client'
import type { DefaultModelsConfig } from '../types'

export interface MigrationStatus {
  can_migrate: boolean
  app_empty: boolean
  web_has_data: boolean
  source_dir: string | null
  target_dir: string
}

export const settingsApi = {
  getDefaultModels: () => api.get<DefaultModelsConfig>('/settings/default-models'),

  setDefaultModels: (data: DefaultModelsConfig) => api.put<DefaultModelsConfig>('/settings/default-models', data),

  getSetting: (key: string) => api.get(`/settings/${key}`),

  setSetting: (key: string, value: Record<string, unknown>) => api.put(`/settings/${key}`, value),

  getMigrationStatus: () => api.get<MigrationStatus>('/migration-status'),

  importData: () => api.post<{ success: boolean; message: string }>('/import-data'),
}
