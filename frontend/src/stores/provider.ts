import { defineStore } from 'pinia'
import { ref } from 'vue'
import { providerApi } from '../api/apiProvider'
import type { ApiProvider, ApiProviderCreate, ApiProviderUpdate } from '../types'

export const useProviderStore = defineStore('provider', () => {
  const providers = ref<ApiProvider[]>([])
  const loading = ref(false)
  const currentProvider = ref<ApiProvider | null>(null)

  async function fetchProviders(providerType?: string) {
    loading.value = true
    try {
      const { data } = await providerApi.list(providerType)
      providers.value = data
    } catch (e) {
      console.error('Failed to fetch providers:', e)
    } finally {
      loading.value = false
    }
  }

  async function createProvider(data: ApiProviderCreate) {
    try {
      const { data: result } = await providerApi.create(data)
      providers.value.unshift(result)
      return result
    } catch (e) {
      console.error('Failed to create provider:', e)
      throw e
    }
  }

  async function updateProvider(id: string, data: ApiProviderUpdate) {
    try {
      const { data: result } = await providerApi.update(id, data)
      const idx = providers.value.findIndex((p) => p.id === id)
      if (idx !== -1) providers.value[idx] = result
      return result
    } catch (e) {
      console.error('Failed to update provider:', e)
      throw e
    }
  }

  async function deleteProvider(id: string) {
    try {
      await providerApi.delete(id)
      providers.value = providers.value.filter((p) => p.id !== id)
    } catch (e) {
      console.error('Failed to delete provider:', e)
      throw e
    }
  }

  async function testConnection(id: string) {
    try {
      const { data } = await providerApi.test(id)
      return data
    } catch (e) {
      console.error('Failed to test connection:', e)
      throw e
    }
  }

  return { providers, loading, currentProvider, fetchProviders, createProvider, updateProvider, deleteProvider, testConnection }
})
