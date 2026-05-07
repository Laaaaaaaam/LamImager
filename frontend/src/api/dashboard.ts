import api from './client'

export const dashboardApi = {
  stats: () => api.get<{
    total_sessions: number
    total_images: number
    total_generations: number
    monthly_cost: number
  }>('/dashboard/stats'),
}
