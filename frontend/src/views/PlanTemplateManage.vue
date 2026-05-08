<template>
  <div class="plan-template-manage">
    <div class="page-actions">
      <button class="btn btn-primary" @click="openDrawer()">创建模板</button>
      <button class="btn" @click="openAiGenerate">AI 生成模板</button>
    </div>

    <table v-if="templates.length">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型</th>
          <th>策略</th>
          <th>步骤数</th>
          <th>描述</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in templates" :key="t.id">
          <td>{{ t.name }}</td>
          <td>
            <span class="badge" :class="t.is_builtin ? 'badge-active' : 'badge-inactive'">
              {{ t.is_builtin ? '内置' : '自定义' }}
            </span>
          </td>
          <td>{{ strategyLabel(t.strategy) }}</td>
          <td>{{ (t.steps as any[] || []).length }}</td>
          <td>{{ t.description }}</td>
          <td class="actions-cell">
            <button class="btn btn-sm" @click="openDrawer(t)">编辑</button>
            <button v-if="!t.is_builtin" class="btn btn-sm btn-danger" @click="removeTemplate(t.id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty-state">
      <p>暂无模板</p>
    </div>

    <!-- 编辑/创建抽屉 -->
    <div v-if="drawerOpen" class="drawer-overlay" @click.self="drawerOpen = false">
      <div class="drawer">
        <div class="drawer-header">
          <h3>{{ editingTemplate ? '编辑模板' : '创建模板' }}</h3>
          <button class="btn btn-sm" @click="drawerOpen = false">关闭</button>
        </div>
        <div class="form-group">
          <label>名称</label>
          <input v-model="form.name" type="text" />
        </div>
        <div class="form-group">
          <label>描述</label>
          <textarea v-model="form.description" rows="2"></textarea>
        </div>
        <div class="form-group">
          <label>执行策略</label>
          <select v-model="form.strategy">
            <option value="parallel">并发生成（批量探索）</option>
            <option value="iterative">顺序迭代（逐步精修）</option>
          </select>
        </div>
        <div class="form-group">
          <label>步骤 (JSON)</label>
          <textarea v-model="stepsJson" rows="8" placeholder='[{"prompt": "...", "negative_prompt": "", "description": "步骤1", "image_count": 1}]'></textarea>
        </div>
        <div class="form-group">
          <label>变量 (JSON)</label>
          <textarea v-model="variablesJson" rows="4" placeholder='[{"key": "subject", "type": "string", "label": "主题", "default": ""}]'></textarea>
        </div>
        <button class="btn btn-primary" style="width: 100%" @click="saveTemplate">
          {{ editingTemplate ? '更新' : '创建' }}
        </button>
      </div>
    </div>

    <!-- AI 生成抽屉 -->
    <div v-if="aiDrawerOpen" class="drawer-overlay" @click.self="aiDrawerOpen = false">
      <div class="drawer">
        <div class="drawer-header">
          <h3>AI 生成模板</h3>
          <button class="btn btn-sm" @click="aiDrawerOpen = false">关闭</button>
        </div>
        <div class="form-group">
          <label>描述你想要的模板</label>
          <textarea v-model="aiDescription" rows="4" placeholder="例如：一个产品摄影模板，包含正面、侧面、45度角三个视角，支持自定义产品名称和背景风格"></textarea>
        </div>
        <div class="form-group">
          <label>执行策略</label>
          <select v-model="aiStrategy">
            <option value="parallel">并发生成（批量探索）</option>
            <option value="iterative">顺序迭代（逐步精修）</option>
          </select>
        </div>
        <button class="btn btn-primary" style="width: 100%" @click="generateWithAi" :disabled="!aiDescription.trim() || aiGenerating">
          {{ aiGenerating ? '生成中...' : '生成模板' }}
        </button>
        <div v-if="aiStreamText" class="ai-stream-output">
          <p class="section-title">生成结果</p>
          <div class="stream-text" :class="{ streaming: aiGenerating }">{{ aiStreamText }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { planTemplateApi } from '../api/planTemplate'
import { promptApi } from '../api/prompt'
import { settingsApi } from '../api/settings'
import { useProviderStore } from '../stores/provider'
import type { PlanTemplate } from '../types'
import { dialog } from '../composables/useDialog'

const providerStore = useProviderStore()
const templates = ref<PlanTemplate[]>([])
const drawerOpen = ref(false)
const editingTemplate = ref<PlanTemplate | null>(null)
const stepsJson = ref('[]')
const variablesJson = ref('[]')

const form = reactive({
  name: '',
  description: '',
  strategy: 'parallel' as string,
})

const aiDrawerOpen = ref(false)
const aiDescription = ref('')
const aiStrategy = ref('parallel')
const aiGenerating = ref(false)
const aiStreamText = ref('')

const strategyLabelMap: Record<string, string> = {
  parallel: '并发生成',
  iterative: '顺序迭代',
}

function strategyLabel(key: string) {
  return strategyLabelMap[key] || key
}

onMounted(async () => {
  await loadTemplates()
  await providerStore.fetchProviders()
})

async function loadTemplates() {
  const { data } = await planTemplateApi.list()
  templates.value = data
}

function openDrawer(template?: PlanTemplate) {
  editingTemplate.value = template || null
  if (template) {
    form.name = template.name
    form.description = template.description
    form.strategy = template.strategy
    stepsJson.value = JSON.stringify(template.steps, null, 2)
    variablesJson.value = JSON.stringify(template.variables, null, 2)
  } else {
    form.name = ''
    form.description = ''
    form.strategy = 'parallel'
    stepsJson.value = '[]'
    variablesJson.value = '[]'
  }
  drawerOpen.value = true
}

async function saveTemplate() {
  let steps = []
  let variables = []
  try { steps = JSON.parse(stepsJson.value) } catch { steps = [] }
  try { variables = JSON.parse(variablesJson.value) } catch { variables = [] }

  const data = { ...form, steps, variables }
  if (editingTemplate.value) {
    await planTemplateApi.update(editingTemplate.value.id, data)
  } else {
    await planTemplateApi.create(data)
  }
  await loadTemplates()
  drawerOpen.value = false
}

async function removeTemplate(id: string) {
  if (await dialog.showConfirm('确定删除此模板？')) {
    await planTemplateApi.delete(id)
    await loadTemplates()
  }
}

function openAiGenerate() {
  aiDescription.value = ''
  aiStreamText.value = ''
  aiStrategy.value = 'parallel'
  aiDrawerOpen.value = true
}

async function generateWithAi() {
  if (!aiDescription.value.trim() || aiGenerating.value) return

  let providerId = ''
  try {
    const { data } = await settingsApi.getDefaultModels()
    providerId = data.default_plan_provider_id || ''
  } catch { /* ignore */ }
  if (!providerId) {
    const llmProviders = providerStore.providers.filter(p => p.provider_type === 'llm' && p.is_active)
    if (!llmProviders.length) {
      dialog.showAlert('请先在设置中配置 LLM 提供商')
      return
    }
    providerId = llmProviders[0].id
  }

  aiGenerating.value = true
  aiStreamText.value = ''

  const systemPrompt = `你是一个AI图像生成模板设计师。根据用户描述，生成一个规划模板的JSON结构。

模板结构要求：
{
  "name": "模板名称",
  "description": "模板描述",
  "strategy": "${aiStrategy.value}",
  "steps": [
    {
      "prompt": "英文提示词，使用 {{variable_key}} 作为变量占位符",
      "negative_prompt": "需要避免的元素",
      "description": "中文步骤说明",
      "image_count": 1,
      "image_size": "1024x1024"
    }
  ],
  "variables": [
    {
      "key": "variable_key",
      "type": "string",
      "label": "变量中文标签",
      "default": "默认值",
      "required": true
    }
  ]
}

规则：
1. prompt 用英文撰写，具体且描述性强
2. 使用 {{variable_key}} 占位符标记可替换的部分
3. variables 数组列出所有使用的变量
4. variable 的 type 可以是 "string"、"select"、"number"
5. 如果 type 是 "select"，需要提供 "options" 数组
6. 只输出 JSON 对象，不要其他文字`

  let fullContent = ''
  try {
    const stream = promptApi.streamChat(
      [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: aiDescription.value },
      ],
      providerId,
      null,
      0.7,
    )

    for await (const token of stream) {
      fullContent += token
      aiStreamText.value = fullContent
    }

    // 解析结果
    const jsonMatch = fullContent.match(/\{[\s\S]*\}/)
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0])
      // 填入创建表单
      form.name = parsed.name || ''
      form.description = parsed.description || ''
      form.strategy = parsed.strategy || aiStrategy.value
      stepsJson.value = JSON.stringify(parsed.steps || [], null, 2)
      variablesJson.value = JSON.stringify(parsed.variables || [], null, 2)
      editingTemplate.value = null
      aiDrawerOpen.value = false
      drawerOpen.value = true
    } else {
      dialog.showAlert('LLM 返回格式无法解析，请重试或手动编辑')
    }
  } catch (e: any) {
    dialog.showAlert('生成失败: ' + (e.message || '未知错误'))
  } finally {
    aiGenerating.value = false
  }
}
</script>

<style scoped>
.page-actions { display: flex; justify-content: flex-end; margin-bottom: 16px; gap: 8px; }
.actions-cell { display: flex; gap: 6px; }
.ai-stream-output { margin-top: 12px; }
.section-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; color: var(--text-secondary); }
.stream-text { font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 8px; max-height: 300px; overflow-y: auto; }
.stream-text.streaming { border-color: #000; animation: pulse-border 1.5s ease-in-out infinite; }
@keyframes pulse-border { 0%, 100% { border-color: #000; } 50% { border-color: #ccc; } }
</style>
