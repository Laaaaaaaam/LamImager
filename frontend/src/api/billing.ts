import api from './client'
import type { BillingSummary, BillingRecord } from '../types'

export const billingApi = {
  summary: () => api.get<BillingSummary>('/billing/summary'),
  details: (params?: { start_date?: string; end_date?: string; provider_id?: string; page?: number; page_size?: number }) =>
    api.get<{ total: number; page: number; page_size: number; records: BillingRecord[] }>('/billing/details', { params }),
  exportCsv: (params?: { start_date?: string; end_date?: string }) =>
    api.get('/billing/export', { params, responseType: 'blob' }),
}
