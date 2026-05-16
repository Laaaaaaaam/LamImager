<template>
  <div class="assistant-sidebar" v-if="show" :class="{ expanded: internalExpanded }">
    <div class="assistant-header">
      <div class="assistant-tabs">
        <button
          v-for="tab in tabs" :key="tab.key"
          class="tab-btn"
          :class="{ active: internalActiveTab === tab.key }"
          @click="internalActiveTab = tab.key"
        >{{ tab.label }}</button>
      </div>
      <div class="assistant-header-actions">
        <button class="btn btn-sm assistant-toggle-btn" @click="internalExpanded = !internalExpanded" :title="internalExpanded ? '收缩' : '展开'">
          <svg v-if="internalExpanded" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <button class="btn btn-sm" @click="$emit('close')">关闭</button>
      </div>
    </div>

    <div class="assistant-content">
      <div v-if="internalActiveTab === 'dialog'" class="tab-dialog">
        <div class="dialog-config-bar">
          <div class="context-toggle" style="border: none; margin-bottom: 0;">
            <button
              class="toggle-btn"
              :class="{ active: responseStyle === 'default' }"
              @click="$emit('update:responseStyle', 'default')"
            >默认</button>
            <button
              class="toggle-btn"
              :class="{ active: responseStyle === 'verbose' }"
              @click="$emit('update:responseStyle', 'verbose')"
            >详细</button>
            <button
              class="toggle-btn"
              :class="{ active: responseStyle === 'concise' }"
              @click="$emit('update:responseStyle', 'concise')"
            >简洁</button>
          </div>
          <button class="dialog-settings-btn" :class="{ active: showDialogSettings }" @click="showDialogSettings = !showDialogSettings" title="更多设置">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          </button>
        </div>
        <div v-if="showDialogSettings" class="dialog-settings-panel">
          <div class="context-toggle">
            <button class="toggle-btn" :class="{ active: contextMode === 'shared' }" @click="$emit('update:contextMode', 'shared')">共享上下文</button>
            <button class="toggle-btn" :class="{ active: contextMode === 'current' }" @click="$emit('update:contextMode', 'current')">仅当前输入</button>
          </div>
          <div class="context-toggle" style="margin-top: 6px;">
            <button class="toggle-btn" :class="{ active: memoryMode === 'global' }" @click="$emit('update:memoryMode', 'global')">全局跨窗口</button>
            <button class="toggle-btn" :class="{ active: memoryMode === 'session' }" @click="$emit('update:memoryMode', 'session')">仅当前会话</button>
          </div>
        </div>
        <div class="dialog-messages" ref="dialogContainer">
          <div v-for="m in dialogMessages" :key="m.id" class="dialog-msg" :class="m.role">
            <template v-if="m.attachments && m.attachments.length">
              <div class="msg-attachments">
                <img v-for="(att, i) in m.attachments" :key="i" v-if="att.type.startsWith('image/')" :src="att.preview" class="msg-attachment-thumb" />
              </div>
            </template>
            <div class="dialog-msg-content" v-html="renderMarkdown(m.content)"></div>
            <button class="dialog-msg-copy" @click="$emit('copy-clipboard', m.content)" title="复制">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
          </div>
        </div>
        <div v-if="dialogToolCalls.length" class="tool-calls-area">
          <div v-for="tc in dialogToolCalls" :key="tc.id" class="tool-call-card" :class="{ collapsed: tc.collapsed }">
            <div class="tool-call-header" @click="tc.collapsed = !tc.collapsed">
              <span class="tool-call-badge">{{ tc.name === 'web_search' ? '搜索' : tc.name === 'image_search' ? '图片搜索' : tc.name }}</span>
              <span class="tool-call-status">{{ tc.content ? '完成' : '执行中...' }}</span>
            </div>
            <div v-if="!tc.collapsed" class="tool-call-body">
              <div v-if="tc.content" class="tool-call-content">{{ tc.content }}</div>
              <div v-else class="tool-call-loading">搜索中...</div>
            </div>
          </div>
        </div>
        <div class="dialog-actions">
          <button class="btn btn-sm" @click="$emit('save-dialog')" :disabled="!dialogMessages.length">保存对话</button>
          <button class="btn btn-sm" @click="$emit('clear-dialog')" :disabled="!dialogMessages.length">清除对话</button>
        </div>
        <div class="dialog-input-area" :class="{ 'drag-over': isDragOverDialog }"
             @dragenter.prevent="isDragOverDialog = true"
             @dragover.prevent
             @dragleave.prevent="isDragOverDialog = false"
             @drop.prevent="onDropDialog">
          <div v-if="isDragOverDialog" class="drag-overlay dialog-drag-overlay">
            <span class="drag-overlay-text">释放以添加文件</span>
          </div>
          <div class="dialog-attachment-preview" v-if="dialogAttachments.length">
            <div v-for="(file, i) in dialogAttachments" :key="i" class="dialog-attachment-item">
              <img v-if="file.type.startsWith('image/')" :src="file.preview" class="dialog-attachment-thumb" />
              <span v-else class="dialog-attachment-doc">{{ file.name }}</span>
              <button class="dialog-attachment-remove" @click="dialogAttachments.splice(i, 1)">x</button>
            </div>
          </div>
          <div class="dialog-input-row">
            <label class="dialog-upload-btn" title="上传文件">
              <input type="file" accept="image/*,.txt,.md" multiple @change="onDialogFileUpload" hidden />
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
            </label>
            <button class="search-toggle-btn" :class="{ active: searchEnabled }" @click="$emit('update:searchEnabled', !searchEnabled)" title="网络搜索">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            </button>
            <textarea
              ref="dialogTextarea"
              v-model="dialogInput"
              placeholder="输入消息..."
              class="dialog-textarea"
              rows="1"
              @keydown.enter.exact.prevent="$emit('send-dialog')"
              @input="autoResizeDialogTextarea"
            />
            <button class="btn btn-sm btn-primary" @click="$emit('send-dialog')" :disabled="!dialogInput.trim() && !dialogAttachments.length">发送</button>
          </div>
        </div>
      </div>

      <div v-if="internalActiveTab === 'optimize'" class="tab-optimize">
        <div class="optimize-directions">
          <p class="section-title">优化方向（可多选）</p>
          <label v-for="dir in optimizeDirections" :key="dir.key" class="direction-item">
            <input type="checkbox" :value="dir.key" :checked="selectedDirections.includes(dir.key)" @change="toggleDirection(dir.key)" />
            <div class="direction-info">
              <span class="direction-name">{{ dir.label }}</span>
              <span class="direction-desc">{{ dir.desc }}</span>
            </div>
          </label>
          <label class="direction-item">
            <input type="checkbox" :checked="selectedDirections.includes('custom')" @change="toggleDirection('custom')" />
            <div class="direction-info">
              <span class="direction-name">自定义</span>
              <span class="direction-desc">输入自定义优化指令</span>
            </div>
          </label>
          <textarea
            v-if="selectedDirections.includes('custom')"
            v-model="customInstruction"
            placeholder="输入自定义优化指令..."
            rows="2"
            class="custom-input"
          ></textarea>
        </div>
        <div class="optimize-preview">
          <p class="section-title">当前提示词</p>
          <div class="preview-text">{{ inputText || '（输入框为空）' }}</div>
        </div>
        <button class="btn btn-primary" style="width: 100%" @click="$emit('do-optimize')" :disabled="!selectedDirections.length || !inputText.trim() || optimizing">
          {{ optimizing ? '优化中...' : '优化' }}
        </button>
        <div v-if="optimizeResult" class="optimize-result">
          <p class="section-title">优化结果</p>
          <div class="result-text" :class="{ streaming: optimizing }">{{ optimizeResult }}</div>
          <button v-if="!optimizing" class="btn btn-sm" @click="$emit('apply-optimize')" style="margin-top: 8px">应用优化</button>
        </div>
      </div>

      <div v-if="internalActiveTab === 'plan'" class="tab-plan">
        <div class="plan-template-section">
          <select :value="selectedTemplateId" class="template-select" @change="$emit('load-template', ($event.target as HTMLSelectElement).value)">
            <option value="">从零开始规划</option>
            <option v-for="t in planTemplates" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>
        <div v-if="templateVariables.length" class="template-variables">
          <div v-for="v in templateVariables" :key="v.key" class="form-group">
            <label>{{ v.label }}{{ v.required ? ' *' : '' }}</label>
            <input :value="templateVariableValues[v.key] || ''" @input="$emit('update-template-var', { key: v.key, value: ($event.target as HTMLInputElement).value })" :placeholder="v.default" type="text" />
          </div>
          <button class="btn btn-sm" @click="$emit('apply-template-variables')">应用变量</button>
        </div>
        <button class="btn btn-primary" style="width: 100%; margin-bottom: 12px" @click="$emit('do-plan')" :disabled="!inputText.trim() || planning">
          {{ planning ? '规划中...' : '生成规划' }}
        </button>
        <div v-if="planning && planStreamText" class="plan-streaming">
          <p class="section-title">正在规划...</p>
          <div class="stream-text">{{ planStreamText }}</div>
        </div>
        <div v-if="planSteps.length" class="plan-steps">
          <div v-for="(step, i) in planSteps" :key="i" class="plan-step">
            <div class="step-header">
              <span>步骤 {{ i + 1 }}</span>
              <div class="step-actions">
                <button class="btn-icon" title="上移" @click="$emit('move-step', i, -1)" :disabled="i === 0">↑</button>
                <button class="btn-icon" title="下移" @click="$emit('move-step', i, 1)" :disabled="i === planSteps.length - 1">↓</button>
                <button class="btn-icon" title="复制" @click="$emit('duplicate-step', i)">⧉</button>
                <button class="btn-icon" title="删除" @click="$emit('remove-step', i)">×</button>
              </div>
            </div>
            <div class="form-group">
              <label>提示词</label>
              <textarea :value="step.prompt" @input="updateStepField(i, 'prompt', ($event.target as HTMLTextAreaElement).value)" rows="2"></textarea>
            </div>
            <div class="form-group">
              <label>反向提示词</label>
              <input :value="step.negative_prompt" @input="updateStepField(i, 'negative_prompt', ($event.target as HTMLInputElement).value)" type="text" />
            </div>
            <div class="form-group form-row">
              <label>数量 <input type="number" :value="step.image_count" @input="updateStepField(i, 'image_count', Number(($event.target as HTMLInputElement).value))" min="1" max="8" style="width:50px" /></label>
              <label>尺寸 <input :value="step.image_size" @input="updateStepField(i, 'image_size', ($event.target as HTMLInputElement).value)" type="text" :placeholder="noSizeLimit ? '不限' : `${imageWidth}x${imageHeight}`" style="width:100px" /></label>
            </div>
            <div class="form-group" v-if="step.description">
              <label>说明</label>
              <p class="step-desc">{{ step.description }}</p>
            </div>
          </div>
          <button class="btn btn-sm" @click="$emit('add-step')">+ 添加步骤</button>
          <div class="plan-summary">
            预计生成: {{ planSteps.reduce((sum, s) => sum + (s.image_count || 1), 0) }} 张图片
          </div>
          <button class="btn btn-primary" style="width: 100%" @click="$emit('execute-plan')">确认并执行</button>
          <button class="btn btn-sm" style="width: 100%; margin-top: 6px" @click="$emit('save-as-template')">保存为模板</button>
        </div>
      </div>

      <div v-if="internalActiveTab === 'skill'" class="tab-skills">
        <p class="section-title">选择技能（可多选）</p>
        <div v-if="skills.length">
          <div v-for="skill in skills" :key="skill.id" class="skill-item">
            <label class="skill-label">
              <input type="checkbox" :value="skill.id" :checked="selectedSkillIds.includes(skill.id)" @change="toggleSkill(skill.id)" />
              <div class="skill-info">
                <span class="skill-name">{{ skill.name }}</span>
                <span class="skill-desc">{{ skill.description }}</span>
              </div>
            </label>
          </div>
        </div>
        <div v-else class="empty-hint">暂无技能，请在技能管理中创建</div>
        <p class="hint-text">已选技能将应用于下次生图指令</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { renderMarkdown } from '../../composables/useMarkdown'
import type { Attachment, DialogToolCall } from '../../types'

interface PlanStep {
  prompt: string
  negative_prompt: string
  description: string
  image_count: number
  image_size: string
}

interface PlanTemplate {
  id: string
  name: string
  [key: string]: any
}

interface TemplateVariable {
  key: string
  label: string
  default?: string
  required?: boolean
}

interface Skill {
  id: string
  name: string
  description: string
  [key: string]: any
}

interface DialogMessage {
  id: number
  role: string
  content: string
  attachments?: Attachment[]
}

const props = defineProps<{
  show: boolean
  tabs: Array<{ key: string; label: string }>
  responseStyle: string
  contextMode: string
  memoryMode: string
  searchEnabled: boolean
  optimizeDirections: Array<{ key: string; label: string; desc: string }>
  optimizing: boolean
  optimizeResult: string
  inputText: string
  imageWidth: number
  imageHeight: number
  noSizeLimit: boolean
  planTemplates: PlanTemplate[]
  selectedTemplateId: string
  templateVariables: TemplateVariable[]
  templateVariableValues: Record<string, string>
  planSteps: PlanStep[]
  planning: boolean
  planStreamText: string
  skills: Skill[]
}>()

const emit = defineEmits<{
  close: []
  'update:responseStyle': [style: string]
  'update:contextMode': [mode: string]
  'update:memoryMode': [mode: string]
  'update:searchEnabled': [enabled: boolean]
  'copy-clipboard': [text: string]
  'save-dialog': []
  'clear-dialog': []
  'send-dialog': []
  'do-optimize': []
  'apply-optimize': []
  'load-template': [id: string]
  'update-template-var': [payload: { key: string; value: string }]
  'apply-template-variables': []
  'do-plan': []
  'move-step': [index: number, direction: number]
  'duplicate-step': [index: number]
  'remove-step': [index: number]
  'add-step': []
  'execute-plan': []
  'save-as-template': []
  'update-plan-step': [payload: { index: number; field: string; value: any }]
  'update:selectedDirections': [dirs: string[]]
  'update:selectedSkillIds': [ids: string[]]
  'dialog-attachments-changed': [attachments: Attachment[]]
}>()

const internalActiveTab = ref('dialog')
const internalExpanded = ref(false)
const showDialogSettings = ref(false)
const dialogMessages = ref<DialogMessage[]>([])
const dialogInput = ref('')
const dialogAttachments = ref<Attachment[]>([])
const dialogToolCalls = ref<DialogToolCall[]>([])
const isDragOverDialog = ref(false)
const selectedDirections = ref<string[]>([])
const customInstruction = ref('')
const selectedSkillIds = ref<string[]>([])
const dialogTextarea = ref<HTMLTextAreaElement | null>(null)
const dialogContainer = ref<HTMLElement | null>(null)

watch(dialogMessages, (val) => {
  if (props.memoryMode === 'global') {
    localStorage.setItem('assistantDialogHistory', JSON.stringify(val))
  }
  nextTick(() => {
    if (dialogContainer.value) {
      dialogContainer.value.scrollTop = dialogContainer.value.scrollHeight
    }
  })
}, { deep: true })

watch(() => props.memoryMode, (mode) => {
  if (mode === 'global') {
    localStorage.setItem('assistantMemoryMode', mode)
  } else {
    localStorage.removeItem('assistantMemoryMode')
  }
})

function restoreFromLocalStorage() {
  const savedMemoryMode = localStorage.getItem('assistantMemoryMode')
  if (savedMemoryMode) {
    emit('update:memoryMode', savedMemoryMode)
  }
  const savedDialog = localStorage.getItem('assistantDialogHistory')
  if (savedDialog) {
    try {
      dialogMessages.value = JSON.parse(savedDialog)
    } catch {}
  }
}

restoreFromLocalStorage()

function autoResizeDialogTextarea() {
  const textarea = dialogTextarea.value
  if (!textarea) return
  textarea.style.height = 'auto'
  const newHeight = Math.min(textarea.scrollHeight, 120)
  textarea.style.height = newHeight + 'px'
}

function toggleDirection(key: string) {
  const current = [...selectedDirections.value]
  const idx = current.indexOf(key)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(key)
  selectedDirections.value = current
  emit('update:selectedDirections', current)
}

function toggleSkill(id: string) {
  const current = [...selectedSkillIds.value]
  const idx = current.indexOf(id)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(id)
  selectedSkillIds.value = current
  emit('update:selectedSkillIds', current)
}

function updateStepField(index: number, field: string, value: any) {
  emit('update-plan-step', { index, field, value })
}

function onDropDialog(e: DragEvent) {
  isDragOverDialog.value = false
  const files = e.dataTransfer?.files
  if (files) {
    processDialogFiles(files)
  }
}

function onDialogFileUpload(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) {
    processDialogFiles(input.files)
  }
  input.value = ''
}

function processDialogFiles(files: FileList) {
  for (const file of files) {
    if (file.type.startsWith('image/')) {
      const reader = new FileReader()
      reader.onload = (e) => {
        dialogAttachments.value.push({
          type: file.type,
          name: file.name,
          preview: e.target?.result as string,
          file
        })
        emit('dialog-attachments-changed', dialogAttachments.value)
      }
      reader.readAsDataURL(file)
    } else if (file.name.endsWith('.txt') || file.name.endsWith('.md')) {
      const reader = new FileReader()
      reader.onload = (e) => {
        dialogAttachments.value.push({
          type: file.type || 'text/plain',
          name: file.name,
          preview: '',
          file
        })
        emit('dialog-attachments-changed', dialogAttachments.value)
      }
      reader.readAsText(file)
    }
  }
}

function clearDialog() {
  dialogMessages.value = []
  dialogToolCalls.value = []
  if (props.memoryMode === 'global') {
    localStorage.removeItem('assistantDialogHistory')
  }
}

defineExpose({
  dialogMessages,
  dialogInput,
  dialogAttachments,
  dialogToolCalls,
  selectedDirections,
  customInstruction,
  selectedSkillIds,
  clearDialog,
  internalExpanded,
  showDialogSettings,
})
</script>

<style scoped>
.assistant-sidebar {
  width: 300px;
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  background: var(--card);
  flex-shrink: 0;
  transition: width 0.2s;
}

.assistant-sidebar.expanded {
  width: 420px;
}

.assistant-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}

.assistant-tabs {
  display: flex;
  gap: 2px;
}

.tab-btn {
  padding: 4px 10px;
  border: none;
  background: none;
  font-size: 12px;
  cursor: pointer;
  border-radius: var(--radius);
  color: var(--text-secondary);
}

.tab-btn.active {
  background: var(--accent);
  color: #fff;
}

.assistant-header-actions {
  display: flex;
  gap: 4px;
}

.assistant-toggle-btn {
  padding: 2px 6px;
}

.assistant-content {
  flex: 1;
  overflow: hidden;
  padding: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.tab-dialog {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.dialog-config-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.context-toggle {
  display: flex;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.toggle-btn {
  padding: 3px 8px;
  border: none;
  background: var(--card);
  font-size: 11px;
  cursor: pointer;
  color: var(--text-secondary);
}

.toggle-btn.active {
  background: var(--accent);
  color: #fff;
}

.dialog-settings-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 4px;
  border-radius: var(--radius);
}

.dialog-settings-btn.active {
  background: var(--hover);
}

.dialog-settings-panel {
  padding: 8px;
  background: var(--hover);
  border-radius: var(--radius);
  margin-bottom: 8px;
}

.dialog-messages {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 8px;
  min-height: 0;
}

.dialog-msg {
  margin-bottom: 8px;
  position: relative;
}

.dialog-msg.user {
  text-align: right;
}

.dialog-msg.assistant {
  text-align: left;
}

.dialog-msg-content {
  display: inline-block;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
  max-width: 100%;
  word-break: break-word;
}

.dialog-msg.user .dialog-msg-content {
  background: var(--hover);
}

.dialog-msg.assistant .dialog-msg-content {
  background: var(--card);
  border: 1px solid var(--border);
}

.dialog-msg-copy {
  position: absolute;
  top: 2px;
  right: 2px;
  background: none;
  border: none;
  cursor: pointer;
  opacity: 0;
  color: var(--text-secondary);
  padding: 2px;
}

.dialog-msg:hover .dialog-msg-copy {
  opacity: 1;
}

.msg-attachments {
  margin-bottom: 4px;
}

.msg-attachment-thumb {
  width: 60px;
  height: 60px;
  object-fit: cover;
  border-radius: var(--radius);
  margin-right: 4px;
}

.tool-calls-area {
  margin-bottom: 8px;
}

.tool-call-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 4px;
  overflow: hidden;
}

.tool-call-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  background: var(--hover);
  cursor: pointer;
  font-size: 11px;
}

.tool-call-badge {
  font-weight: 600;
}

.tool-call-status {
  color: var(--text-secondary);
}

.tool-call-body {
  padding: 6px 8px;
  font-size: 11px;
}

.tool-call-content {
  white-space: pre-wrap;
  max-height: 100px;
  overflow: auto;
}

.tool-call-loading {
  color: var(--text-secondary);
}

.dialog-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.dialog-input-area {
  position: relative;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px;
  margin-top: auto;
  flex-shrink: 0;
}

.dialog-input-area.drag-over {
  border-color: var(--accent);
  background: var(--hover);
}

.dialog-attachment-preview {
  display: flex;
  gap: 4px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.dialog-attachment-item {
  position: relative;
}

.dialog-attachment-thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 3px;
}

.dialog-attachment-doc {
  font-size: 10px;
  padding: 2px 4px;
  background: var(--hover);
  border-radius: 3px;
}

.dialog-attachment-remove {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--danger);
  color: white;
  border: none;
  font-size: 9px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.dialog-input-row {
  display: flex;
  gap: 4px;
  align-items: flex-end;
}

.dialog-upload-btn {
  display: flex;
  align-items: center;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 4px;
}

.dialog-textarea {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 4px 8px;
  font-size: 13px;
  resize: none;
  outline: none;
  max-height: 120px;
  font-family: inherit;
}

.dialog-textarea:focus {
  border-color: var(--accent);
}

.search-toggle-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--text-secondary);
  padding: 4px;
}

.search-toggle-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-secondary);
}

.optimize-directions {
  margin-bottom: 12px;
}

.tab-optimize,
.tab-plan,
.tab-skills {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.direction-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
  cursor: pointer;
}

.direction-info {
  display: flex;
  flex-direction: column;
}

.direction-name {
  font-size: 12px;
  font-weight: 500;
}

.direction-desc {
  font-size: 11px;
  color: var(--text-secondary);
}

.custom-input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 12px;
  margin-top: 6px;
  resize: vertical;
  font-family: inherit;
}

.optimize-preview {
  margin-bottom: 12px;
}

.preview-text {
  font-size: 12px;
  padding: 8px;
  background: var(--hover);
  border-radius: var(--radius);
  max-height: 80px;
  overflow: auto;
}

.optimize-result {
  margin-top: 12px;
}

.result-text {
  font-size: 12px;
  padding: 8px;
  background: var(--hover);
  border-radius: var(--radius);
  white-space: pre-wrap;
  max-height: 200px;
  overflow: auto;
}

.result-text.streaming {
  border: 1px solid var(--accent);
  animation: pulse-border 1.5s infinite;
}

@keyframes pulse-border {
  0%, 100% { border-color: var(--accent); }
  50% { border-color: transparent; }
}

.plan-template-section {
  margin-bottom: 12px;
}

.template-select {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 12px;
  background: var(--card);
}

.template-variables {
  margin-bottom: 12px;
  padding: 8px;
  background: var(--hover);
  border-radius: var(--radius);
}

.form-group {
  margin-bottom: 8px;
}

.form-group label {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 2px;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 12px;
  font-family: inherit;
}

.form-row {
  display: flex;
  gap: 8px;
}

.form-row label {
  display: flex;
  align-items: center;
  gap: 4px;
}

.plan-streaming {
  margin-bottom: 12px;
}

.stream-text {
  font-size: 12px;
  padding: 8px;
  background: var(--hover);
  border-radius: var(--radius);
  border: 1px solid var(--accent);
  animation: pulse-border 1.5s infinite;
  white-space: pre-wrap;
  max-height: 150px;
  overflow: auto;
}

.plan-steps {
  margin-top: 12px;
}

.plan-step {
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 8px;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
}

.step-actions {
  display: flex;
  gap: 2px;
}

.btn-icon {
  background: none;
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
  padding: 2px 6px;
  font-size: 12px;
}

.btn-icon:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.step-desc {
  font-size: 11px;
  color: var(--text-secondary);
  margin: 2px 0 0;
}

.plan-summary {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 8px 0;
  text-align: center;
}

.skill-item {
  margin-bottom: 6px;
}

.skill-label {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  cursor: pointer;
}

.skill-info {
  display: flex;
  flex-direction: column;
}

.skill-name {
  font-size: 12px;
  font-weight: 500;
}

.skill-desc {
  font-size: 11px;
  color: var(--text-secondary);
}

.empty-hint {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
  padding: 20px 0;
}

.hint-text {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 12px;
}

.drag-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  border-radius: var(--radius);
}

.dialog-drag-overlay {
  background: rgba(0, 0, 0, 0.05);
}

.drag-overlay-text {
  font-size: 12px;
  color: var(--accent);
  font-weight: 500;
}
</style>
