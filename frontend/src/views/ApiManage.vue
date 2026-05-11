<template>
  <div class="api-manage">
    <div class="page-actions">
      <button class="btn btn-primary" @click="openVendorDrawer()">添加供应商</button>
    </div>

    <div v-if="store.vendors.length">
      <table>
        <thead>
          <tr>
            <th style="width:24px"></th>
            <th>名称</th>
            <th>接口地址</th>
            <th>模型数</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="v in store.vendors" :key="v.id">
            <tr class="vendor-row" @click="toggleVendor(v.id)">
              <td>
                <span class="expand-icon" :class="{ expanded: expandedVendors.has(v.id) }">&#9654;</span>
              </td>
              <td>{{ v.name }}</td>
              <td class="url-cell">{{ v.base_url }}</td>
              <td>{{ v.model_count }}</td>
              <td>
                <span class="badge" :class="v.is_active ? 'badge-active' : 'badge-inactive'">
                  {{ v.is_active ? '启用' : '停用' }}
                </span>
              </td>
              <td class="actions-cell">
                <button class="btn btn-sm" @click.stop="testVendorConn(v.id)">测试</button>
                <button class="btn btn-sm" @click.stop="openVendorDrawer(v)">编辑</button>
                <button class="btn btn-sm btn-danger" @click.stop="removeVendor(v.id)">删除</button>
              </td>
            </tr>
            <tr v-if="expandedVendors.has(v.id)" class="model-section">
              <td colspan="6">
                <div class="model-header">
                  <span class="model-title">模型列表</span>
                  <button class="btn btn-sm btn-primary" @click="openModelDrawer(v)">添加模型</button>
                </div>
                <table class="model-table" v-if="getVendorModels(v.id).length">
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th>模型ID</th>
                      <th>类型</th>
                      <th>计费</th>
                      <th>状态</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="m in getVendorModels(v.id)" :key="m.id">
                      <td>{{ m.nickname || m.model_id }}</td>
                      <td>{{ m.model_id }}</td>
                      <td>
                        <span class="badge" :class="m.provider_type === 'llm' ? 'badge-active' : m.provider_type === 'web_search' ? 'badge-tool' : 'badge-running'">
                          {{ m.provider_type === 'llm' ? 'LLM' : m.provider_type === 'web_search' ? '联网搜索' : '图像生成' }}
                        </span>
                      </td>
                      <td>{{ m.billing_type === 'per_call' ? '按次' : '按Token' }} / {{ m.unit_price }}</td>
                      <td>
                        <span class="badge" :class="m.is_active ? 'badge-active' : 'badge-inactive'">
                          {{ m.is_active ? '启用' : '停用' }}
                        </span>
                      </td>
                      <td class="actions-cell">
                        <button class="btn btn-sm" @click.stop="testConn(m.id)">测试</button>
                        <button class="btn btn-sm" @click.stop="openModelDrawer(v, m)">编辑</button>
                        <button class="btn btn-sm btn-danger" @click.stop="removeProvider(m.id)">删除</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <div v-else class="model-empty">暂无模型，点击"添加模型"开始</div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div v-else-if="!store.loading" class="empty-state">
      <p>暂无API供应商</p>
      <button class="btn btn-primary" @click="openVendorDrawer()">添加供应商</button>
    </div>

    <!-- Vendor Drawer -->
    <div v-if="vendorDrawerOpen" class="drawer-overlay" @click.self="vendorDrawerOpen = false">
      <div class="drawer">
        <div class="drawer-header">
          <h3>{{ editingVendor ? '编辑供应商' : '添加供应商' }}</h3>
          <button class="btn btn-sm" @click="vendorDrawerOpen = false">关闭</button>
        </div>
        <div class="form-group">
          <label>名称</label>
          <input v-model="vendorForm.name" type="text" placeholder="供应商名称" />
        </div>
        <div class="form-group">
          <label>接口地址</label>
          <input v-model="vendorForm.base_url" type="url" placeholder="https://api.openai.com" />
        </div>
        <div class="form-group">
          <label>API密钥</label>
          <input v-model="vendorForm.api_key" type="password" :placeholder="editingVendor ? '留空保持不变' : 'sk-...'" />
        </div>
        <div class="form-group">
          <label>
            <input v-model="vendorForm.is_active" type="checkbox" /> 启用
          </label>
        </div>
        <button class="btn btn-primary" style="width: 100%" @click="saveVendor">
          {{ editingVendor ? '更新' : '创建' }}
        </button>
        <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
          {{ testResult.message }}
        </div>
      </div>
    </div>

    <!-- Model Drawer -->
    <div v-if="modelDrawerOpen" class="drawer-overlay" @click.self="modelDrawerOpen = false">
      <div class="drawer">
        <div class="drawer-header">
          <h3>{{ editingModel ? '编辑模型' : '添加模型' }} - {{ modelVendor?.name }}</h3>
          <button class="btn btn-sm" @click="modelDrawerOpen = false">关闭</button>
        </div>
        <div class="form-group">
          <label>名称</label>
          <input v-model="modelForm.nickname" type="text" placeholder="显示名称" />
        </div>
        <div class="form-group">
          <label>模型ID</label>
          <input v-model="modelForm.model_id" type="text" placeholder="gpt-4o" />
        </div>
        <div class="form-group">
          <label>类型</label>
          <select v-model="modelForm.provider_type">
            <option value="llm">LLM</option>
            <option value="image_gen">图像生成</option>
            <option value="web_search">联网搜索</option>
          </select>
        </div>
        <div class="form-group">
          <label>计费方式</label>
          <select v-model="modelForm.billing_type">
            <option value="per_call">按次计费</option>
            <option value="per_token">按Token计费</option>
          </select>
        </div>
        <div class="form-group">
          <label>单价</label>
          <input v-model.number="modelForm.unit_price" type="number" step="0.000001" min="0" />
        </div>
        <div class="form-group">
          <label>货币</label>
          <select v-model="modelForm.currency">
            <option value="CNY">CNY</option>
            <option value="USD">USD</option>
          </select>
        </div>
        <div class="form-group">
          <label>
            <input v-model="modelForm.is_active" type="checkbox" /> 启用
          </label>
        </div>
        <button class="btn btn-primary" style="width: 100%" @click="saveModel">
          {{ editingModel ? '更新' : '创建' }}
        </button>
        <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
          {{ testResult.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { useProviderStore } from '../stores/provider'
import type { ApiProvider, ApiVendor } from '../types'
import { dialog } from '../composables/useDialog'

const store = useProviderStore()
const expandedVendors = ref<Set<string>>(new Set())
const testResult = ref<{ success: boolean; message: string } | null>(null)

// Vendor form state
const vendorDrawerOpen = ref(false)
const editingVendor = ref<ApiVendor | null>(null)

const vendorForm = reactive({
  name: '',
  base_url: '',
  api_key: '',
  is_active: true,
})

// Model form state
const modelDrawerOpen = ref(false)
const modelVendor = ref<ApiVendor | null>(null)
const editingModel = ref<ApiProvider | null>(null)

const modelForm = reactive({
  nickname: '',
  model_id: '',
  provider_type: 'llm' as 'llm' | 'image_gen' | 'web_search',
  billing_type: 'per_call' as 'per_call' | 'per_token',
  unit_price: 0,
  currency: 'CNY',
  is_active: true,
})

onMounted(async () => {
  await store.fetchVendors()
  await store.fetchProviders()
})

function toggleVendor(id: string) {
  if (expandedVendors.value.has(id)) {
    expandedVendors.value.delete(id)
    expandedVendors.value = new Set(expandedVendors.value)
  } else {
    expandedVendors.value = new Set(expandedVendors.value).add(id)
  }
}

function getVendorModels(vendorId: string): ApiProvider[] {
  return store.providers.filter(p => p.vendor_id === vendorId)
}

function openVendorDrawer(vendor?: ApiVendor) {
  editingVendor.value = vendor || null
  testResult.value = null
  if (vendor) {
    Object.assign(vendorForm, {
      name: vendor.name,
      base_url: vendor.base_url,
      api_key: '',
      is_active: vendor.is_active,
    })
  } else {
    Object.assign(vendorForm, {
      name: '', base_url: '', api_key: '', is_active: true,
    })
  }
  vendorDrawerOpen.value = true
}

async function saveVendor() {
  try {
    if (editingVendor.value) {
      const data: Record<string, unknown> = { ...vendorForm }
      if (!vendorForm.api_key) delete data.api_key
      await store.updateVendor(editingVendor.value.id, data)
    } else {
      await store.createVendor({ ...vendorForm })
    }
    vendorDrawerOpen.value = false
  } catch (e: any) {
    dialog.showAlert(e.response?.data?.detail || e.message || '操作失败')
  }
}

async function testVendorConn(id: string) {
  testResult.value = null
  try {
    const result = await store.testVendor(id)
    testResult.value = result as any
  } catch (e: any) {
    testResult.value = { success: false, message: e.message || '测试失败' }
  }
}

async function removeVendor(id: string) {
  if (await dialog.showConfirm('确定删除此供应商及其所有模型？')) {
    await store.deleteVendor(id)
    await store.fetchProviders()
  }
}

function openModelDrawer(vendor: ApiVendor, model?: ApiProvider) {
  modelVendor.value = vendor
  editingModel.value = model || null
  testResult.value = null
  if (model) {
    Object.assign(modelForm, {
      nickname: model.nickname || model.model_id,
      model_id: model.model_id,
      provider_type: model.provider_type,
      billing_type: model.billing_type,
      unit_price: model.unit_price,
      currency: model.currency,
      is_active: model.is_active,
    })
  } else {
    Object.assign(modelForm, {
      nickname: '', model_id: '',
      provider_type: 'llm', billing_type: 'per_call', unit_price: 0, currency: 'CNY', is_active: true,
    })
  }
  modelDrawerOpen.value = true
}

async function saveModel() {
  if (!modelVendor.value) return
  try {
    if (editingModel.value) {
      await store.updateProvider(editingModel.value.id, { ...modelForm })
    } else {
      await store.createProvider({
        ...modelForm,
        vendor_id: modelVendor.value.id,
      })
    }
    await store.fetchProviders()
    await store.fetchVendors()
    modelDrawerOpen.value = false
  } catch (e: any) {
    dialog.showAlert(e.response?.data?.detail || e.message || '操作失败')
  }
}

async function testConn(id: string) {
  testResult.value = null
  try {
    const result = await store.testConnection(id)
    testResult.value = result as any
  } catch (e: any) {
    testResult.value = { success: false, message: e.message || '测试失败' }
  }
}

async function removeProvider(id: string) {
  if (await dialog.showConfirm('确定删除此模型？')) {
    await store.deleteProvider(id)
    await store.fetchVendors()
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
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.actions-cell {
  display: flex;
  gap: 6px;
}
.vendor-row {
  cursor: pointer;
  transition: background 0.15s;
}
.vendor-row:hover {
  background: #f5f5f5;
}
.expand-icon {
  display: inline-block;
  font-size: 10px;
  transition: transform 0.2s;
  color: var(--text-secondary);
}
.expand-icon.expanded {
  transform: rotate(90deg);
}
.model-section td {
  padding: 0;
  background: #fafafa;
}
.model-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
}
.model-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}
.model-table {
  margin: 0;
}
.model-table th {
  font-size: 12px;
  padding: 6px 12px;
  color: var(--text-secondary);
}
.model-table td {
  padding: 6px 12px;
  font-size: 13px;
}
.model-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
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
