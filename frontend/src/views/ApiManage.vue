<template>
  <div class="api-manage">
    <div class="page-actions">
      <button class="btn btn-primary" @click="openDrawer()">添加提供商</button>
    </div>

    <table v-if="providers.length">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型</th>
          <th>模型</th>
          <th>接口地址</th>
          <th>计费</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in providers" :key="p.id">
          <td>{{ p.nickname }}</td>
          <td>
            <span class="badge" :class="p.provider_type === 'llm' ? 'badge-active' : p.provider_type === 'web_search' ? 'badge-tool' : 'badge-running'">
              {{ p.provider_type === 'llm' ? 'LLM' : p.provider_type === 'web_search' ? '联网搜索' : '图像生成' }}
            </span>
          </td>
          <td>{{ p.model_id }}</td>
          <td class="url-cell">{{ p.base_url }}</td>
          <td>{{ p.billing_type === 'per_call' ? '按次' : '按Token' }} / {{ p.unit_price }}</td>
          <td>
            <span class="badge" :class="p.is_active ? 'badge-active' : 'badge-inactive'">
              {{ p.is_active ? '启用' : '停用' }}
            </span>
          </td>
          <td class="actions-cell">
            <button class="btn btn-sm" @click="testConn(p.id)">测试</button>
            <button class="btn btn-sm" @click="openDrawer(p)">编辑</button>
            <button class="btn btn-sm btn-danger" @click="removeProvider(p.id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty-state">
      <p>暂无API提供商</p>
      <button class="btn btn-primary" @click="openDrawer()">添加提供商</button>
    </div>

    <div v-if="drawerOpen" class="drawer-overlay" @click.self="drawerOpen = false">
      <div class="drawer">
        <div class="drawer-header">
          <h3>{{ editingProvider ? '编辑提供商' : '添加提供商' }}</h3>
          <button class="btn btn-sm" @click="drawerOpen = false">关闭</button>
        </div>
        <div class="form-group">
          <label>名称</label>
          <input v-model="form.nickname" type="text" placeholder="API提供商名称" />
        </div>
        <div class="form-group">
          <label>接口地址</label>
          <input v-model="form.base_url" type="url" placeholder="https://api.openai.com" />
        </div>
        <div class="form-group">
          <label>模型ID</label>
          <input v-model="form.model_id" type="text" placeholder="gpt-4o" />
        </div>
        <div class="form-group">
          <label>API密钥</label>
          <input v-model="form.api_key" type="password" :placeholder="editingProvider ? '留空保持不变' : 'sk-...'" />
        </div>
        <div class="form-group">
          <label>提供商类型</label>
          <select v-model="form.provider_type">
            <option value="llm">LLM</option>
            <option value="image_gen">图像生成</option>
            <option value="web_search">联网搜索</option>
          </select>
        </div>
        <div class="form-group">
          <label>计费方式</label>
          <select v-model="form.billing_type">
            <option value="per_call">按次计费</option>
            <option value="per_token">按Token计费</option>
          </select>
        </div>
        <div class="form-group">
          <label>单价</label>
          <input v-model.number="form.unit_price" type="number" step="0.000001" min="0" />
        </div>
        <div class="form-group">
          <label>货币</label>
          <select v-model="form.currency">
            <option value="CNY">CNY</option>
            <option value="USD">USD</option>
          </select>
        </div>
        <div class="form-group">
          <label>
            <input v-model="form.is_active" type="checkbox" /> 启用
          </label>
        </div>
        <button class="btn btn-primary" style="width: 100%" @click="saveProvider">
          {{ editingProvider ? '更新' : '创建' }}
        </button>
        <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
          {{ testResult.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useProviderStore } from '../stores/provider'
import type { ApiProvider } from '../types'
import { dialog } from '../composables/useDialog'

const store = useProviderStore()
const providers = ref<ApiProvider[]>([])
const drawerOpen = ref(false)
const editingProvider = ref<ApiProvider | null>(null)
const testResult = ref<{ success: boolean; message: string } | null>(null)

const form = reactive({
  nickname: '',
  base_url: '',
  model_id: '',
  api_key: '',
  provider_type: 'llm' as 'llm' | 'image_gen' | 'web_search',
  billing_type: 'per_call' as 'per_call' | 'per_token',
  unit_price: 0,
  currency: 'CNY',
  is_active: true,
})

onMounted(async () => {
  await store.fetchProviders()
  providers.value = store.providers
})

function openDrawer(provider?: ApiProvider) {
  editingProvider.value = provider || null
  testResult.value = null
  if (provider) {
    Object.assign(form, {
      nickname: provider.nickname,
      base_url: provider.base_url,
      model_id: provider.model_id,
      api_key: '',
      provider_type: provider.provider_type,
      billing_type: provider.billing_type,
      unit_price: provider.unit_price,
      currency: provider.currency,
      is_active: provider.is_active,
    })
  } else {
    Object.assign(form, {
      nickname: '', base_url: '', model_id: '', api_key: '',
      provider_type: 'llm', billing_type: 'per_call', unit_price: 0, currency: 'CNY', is_active: true,
    })
  }
  drawerOpen.value = true
}

async function saveProvider() {
  try {
    if (editingProvider.value) {
      const updateData: Record<string, unknown> = { ...form }
      if (!form.api_key) delete updateData.api_key
      await store.updateProvider(editingProvider.value.id, updateData)
    } else {
      await store.createProvider({ ...form })
    }
    providers.value = store.providers
    drawerOpen.value = false
  } catch (e: any) {
    dialog.showAlert(e.message || '测试失败')
  }
}

async function testConn(id: string) {
  testResult.value = null
  try {
    const result = await store.testConnection(id)
    testResult.value = result as any
  } catch (e: any) {
    testResult.value = { success: false, message: e.message }
  }
}

async function removeProvider(id: string) {
  if (await dialog.showConfirm('确定删除此提供商？')) {
    await store.deleteProvider(id)
    providers.value = store.providers
  }
}
</script>

<style scoped>
.page-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}
.url-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.actions-cell {
  display: flex;
  gap: 6px;
}
.test-result {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 13px;
}
.test-result.success {
  background: #E8F5E9;
  color: var(--success);
}
.test-result.error {
  background: #FFEBEE;
  color: var(--danger);
}
</style>
