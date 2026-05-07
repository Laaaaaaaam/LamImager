<template>
  <div class="settings-page">
    <div class="settings-section">
      <h3>默认模型配置</h3>
      <div class="form-group">
        <label>提示词优化模型</label>
        <select v-model="defaultModels.default_optimize_provider_id" @change="saveDefaultModels">
          <option value="">未设置</option>
          <option v-for="p in llmProviders" :key="p.id" :value="p.id">{{ p.nickname }} ({{ p.model_id }})</option>
        </select>
        <span class="hint">用于会话中的提示词优化功能</span>
      </div>
      <div class="form-group">
        <label>图像生成模型</label>
        <select v-model="defaultModels.default_image_provider_id" @change="saveDefaultModels">
          <option value="">未设置</option>
          <option v-for="p in imageProviders" :key="p.id" :value="p.id">{{ p.nickname }} ({{ p.model_id }})</option>
        </select>
        <span class="hint">用于会话中的图像生成</span>
      </div>
      <div class="form-group">
        <label>任务规划模型</label>
        <select v-model="defaultModels.default_plan_provider_id" @change="saveDefaultModels">
          <option value="">未设置</option>
          <option v-for="p in llmProviders" :key="p.id" :value="p.id">{{ p.nickname }} ({{ p.model_id }})</option>
        </select>
        <span class="hint">用于会话中的任务规划功能</span>
      </div>
    </div>

    <div class="settings-section">
      <h3>默认图像尺寸</h3>
      <div class="form-group size-row">
        <label>宽度</label>
        <input
          v-model.number="defaultModels.default_image_width"
          type="number"
          min="64"
          step="64"
          @change="saveDefaultModels"
        />
        <span class="size-sep">×</span>
        <label>高度</label>
        <input
          v-model.number="defaultModels.default_image_height"
          type="number"
          min="64"
          step="64"
          @change="saveDefaultModels"
        />
      </div>
      <span class="hint">会话中生图的默认尺寸，具体限制取决于所使用的API</span>
    </div>

    <div class="settings-section">
      <h3>通用设置</h3>
      <div class="form-group">
        <label>最大并发任务数</label>
        <input v-model.number="defaultModels.max_concurrent" type="number" min="1" max="20" @change="saveDefaultModels" />
      </div>
    </div>

    <div class="settings-section">
      <h3>数据管理</h3>
      <div class="data-actions">
        <button class="btn" @click="importData" :disabled="importing">
          {{ importing ? '导入中...' : '从网页版导入数据' }}
        </button>
        <button class="btn btn-danger" @click="clearCache">清除缓存</button>
      </div>
      <div v-if="migrationMsg" class="migration-msg" :class="migrationMsgType">
        {{ migrationMsg }}
      </div>
    </div>

    <div v-if="saveMsg" class="save-msg" :class="{ success: saveMsgType === 'success', error: saveMsgType === 'error' }">
      {{ saveMsg }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useProviderStore } from '../stores/provider'
import { settingsApi } from '../api/settings'
import type { DefaultModelsConfig, ApiProvider } from '../types'
import { dialog } from '../composables/useDialog'

const providerStore = useProviderStore()
const saveMsg = ref('')
const saveMsgType = ref<'success' | 'error'>('success')
const importing = ref(false)
const migrationMsg = ref('')
const migrationMsgType = ref<'success' | 'error'>('success')

const llmProviders = ref<ApiProvider[]>([])
const imageProviders = ref<ApiProvider[]>([])

const defaultModels = reactive<DefaultModelsConfig>({
  default_optimize_provider_id: null,
  default_image_provider_id: null,
  default_plan_provider_id: null,
  default_image_width: 1024,
  default_image_height: 1024,
  max_concurrent: 5,
})

onMounted(async () => {
  await providerStore.fetchProviders()
  llmProviders.value = providerStore.providers.filter(p => p.provider_type === 'llm' && p.is_active)
  imageProviders.value = providerStore.providers.filter(p => p.provider_type === 'image_gen' && p.is_active)
  try {
    const { data } = await settingsApi.getDefaultModels()
    defaultModels.default_optimize_provider_id = data.default_optimize_provider_id
    defaultModels.default_image_provider_id = data.default_image_provider_id
    defaultModels.default_plan_provider_id = data.default_plan_provider_id
    if (data.default_image_width) defaultModels.default_image_width = data.default_image_width
    if (data.default_image_height) defaultModels.default_image_height = data.default_image_height
    if (data.max_concurrent) defaultModels.max_concurrent = data.max_concurrent
  } catch { /* ignore */ }
})

async function saveDefaultModels() {
  try {
    await settingsApi.setDefaultModels({ ...defaultModels })
    showSaveMsg('设置已保存', 'success')
  } catch {
    showSaveMsg('保存失败', 'error')
  }
}

function showSaveMsg(msg: string, type: 'success' | 'error') {
  saveMsg.value = msg
  saveMsgType.value = type
  setTimeout(() => { saveMsg.value = '' }, 2000)
}

async function clearCache() {
  if (await dialog.showConfirm('确定清除所有缓存数据？')) {
    localStorage.clear()
    showSaveMsg('缓存已清除', 'success')
  }
}

async function importData() {
  if (!(await dialog.showConfirm('将从网页版 data/ 目录导入数据到当前应用，导入后需重启生效。确定导入？'))) return
  importing.value = true
  try {
    const { data } = await settingsApi.importData()
    if (data.success) {
      migrationMsg.value = data.message
      migrationMsgType.value = 'success'
    } else {
      migrationMsg.value = data.message
      migrationMsgType.value = 'error'
    }
  } catch (e: any) {
    migrationMsg.value = '导入失败: ' + (e.message || '未知错误')
    migrationMsgType.value = 'error'
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.settings-section {
  margin-bottom: 32px;
}
.settings-section h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.hint {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}
.size-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.size-row label {
  margin: 0;
  font-size: 13px;
}
.size-row input {
  width: 80px;
  text-align: center;
}
.size-sep {
  font-size: 13px;
  color: var(--text-secondary);
}
.save-msg {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 8px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  z-index: 100;
}
.save-msg.success {
  background: #E8F5E9;
  color: var(--success);
}
.save-msg.error {
  background: #FFEBEE;
  color: var(--danger);
}
.data-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.migration-msg {
  margin-top: 8px;
  padding: 6px 12px;
  border-radius: var(--radius);
  font-size: 13px;
}
.migration-msg.success {
  background: #E8F5E9;
  color: var(--success);
}
.migration-msg.error {
  background: #FFEBEE;
  color: var(--danger);
}
</style>
