<template>
  <div class="session-page">
    <div class="session-list" :class="{ collapsed: sessionListCollapsed }">
      <div class="session-list-header">
        <span v-if="!sessionListCollapsed" class="session-list-label">会话</span>
        <button class="session-list-toggle" @click="sessionListCollapsed = !sessionListCollapsed" :title="sessionListCollapsed ? '展开' : '折叠'">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline v-if="sessionListCollapsed" points="9 18 15 12 9 6"/><polyline v-else points="15 18 9 12 15 6"/></svg>
        </button>
      </div>
      <button class="btn btn-primary new-session-btn" @click="newSession" v-if="!sessionListCollapsed">+ 新建会话</button>
      <div class="session-items" v-if="!sessionListCollapsed">
        <div
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === currentSessionId, 'checkpoint-pending': hasCheckpointPending(s.id) }"
          @click="selectSession(s.id)"
          @contextmenu.prevent="showContextMenu($event, s)"
        >
          <div class="session-title-row">
            <span class="session-title">{{ s.title }}</span>
            <span v-if="hasCheckpointPending(s.id)" class="status-badge checkpoint">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> 待确认
            </span>
            <span v-else-if="getSessionStatus(s.id) === 'generating'" class="status-badge generating">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 生成中
            </span>
            <span v-else-if="getSessionStatus(s.id) === 'optimizing'" class="status-badge optimizing">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 优化中
            </span>
            <span v-else-if="getSessionStatus(s.id) === 'planning'" class="status-badge planning">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 规划中
            </span>
            <span v-else-if="getSessionStatus(s.id) === 'error'" class="status-badge error">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> 错误
            </span>
          </div>
          <div class="session-meta">
            <span>{{ s.cost > 0 ? '¥' + s.cost.toFixed(2) : '¥0.00' }}</span>
            <span>{{ formatTokens(s.tokens) }}</span>
            <span v-if="getTaskProgress(s.id)" class="task-progress">{{ getTaskProgress(s.id) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-area">
      <MessageList
        ref="messageListRef"
        :messages="messages"
        :is-busy="!!(currentSessionId && isSessionBusy(currentSessionId))"
        :generating-text="generatingText"
        :task-type-label="currentTaskLabel"
        :progress-text="getTaskProgress(currentSessionId || '')"
        :agent-stream-state="agentStreamState"
        :timeline-messages="timelineMessages"
        :checkpoint-state="agentCheckpointState"
        @copy="copyMessageContent"
        @open-image="openImage"
        @image-context="showImageContextMenu"
        @download-selected="downloadSelected"
        @download-all="(urls: string[]) => downloadAll(urls)"
        @compare-selected="compareSelectedImages"
        @enter-refine="enterRefineMode"
        @apply-optimized="applyOptimized"
        @cancel="cancelAgent"
        @checkpoint-approve="resolveAgentCheckpoint('approve')"
        @checkpoint-retry="resolveAgentCheckpoint('retry_step')"
        @checkpoint-replan="resolveAgentCheckpoint('replan')"
        @checkpoint-cancel="resolveAgentCheckpoint('cancel')"
      />

      <CompareOverlay :images="comparingImages" @close="comparingImages = []" @download-all="downloadAll" />

      <Lightbox :visible="!!lightboxUrl" :image-url="lightboxUrl" @close="lightboxUrl = ''" @download="downloadOne" />

      <div class="input-area" :class="{ 'drag-over': isDragOverMain }"
           @dragenter.prevent="onDragEnterMain"
           @dragover.prevent="onDragOverMain"
           @dragleave.prevent="onDragLeaveMain"
           @drop.prevent="onDropMain">
        <div v-if="isDragOverMain" class="drag-overlay">
          <span class="drag-overlay-text">释放以添加图片或文档</span>
        </div>
        <ComposerControls
          :agent-mode="agentMode" :is-refine-mode="isRefineMode" :is-busy="!!(currentSessionId && isSessionBusy(currentSessionId))"
          :input-text="inputText" :show-assistant="showAssistant"
          :image-count="imageCount" :custom-count="customCount"
          :image-width="imageWidth" :image-height="imageHeight" :no-size-limit="noSizeLimit"
          @exit-refine="exitRefineMode" @toggle-agent="agentMode = !agentMode" @toggle-assistant="showAssistant = !showAssistant"
          @send="sendGenerate" @cancel="cancelAgent"
          @update:image-count="imageCount = $event" @update:custom-count="customCount = $event"
          @update:image-width="imageWidth = $event" @update:image-height="imageHeight = $event"
          @update:no-size-limit="noSizeLimit = $event"
          @open-custom-count="openCustomCount" @clamp-count="clampCount"
          @upload-image="handleFileUpload($event, 'image')" @upload-doc="handleFileUpload($event, 'doc')"
        />
        <div class="input-main">
          <ContextImageStrip v-if="contextImageList.length" :images="contextImageList" @remove="removeContextImage" @add-image="processMainFiles" />
          <textarea
            ref="mainTextarea"
            v-model="inputText"
            :placeholder="isRefineMode ? '基于参考图进行修改...' : '输入生图指令...'"
            rows="2"
            @input="autoResizeTextarea"
            @keydown.enter.exact.prevent="sendGenerate"
            @dragover.stop.prevent="onDragOverMain"
            @drop.stop.prevent="onDropMain"
          ></textarea>
          <input
            v-if="!agentMode"
            v-model="negativePrompt"
            type="text"
            class="negative-input"
            placeholder="反向提示词（可选）"
          />
        </div>
      </div>
    </div>

    <AssistantSidebar
      ref="assistantSidebarRef"
      :show="showAssistant" :tabs="assistantTabs"
      :response-style="responseStyle" :context-mode="contextMode" :memory-mode="memoryMode"
      :search-enabled="searchEnabled"
      :optimize-directions="optimizeDirections"
      :optimizing="optimizing" :optimize-result="optimizeResult"
      :input-text="inputText" :image-width="imageWidth" :image-height="imageHeight" :no-size-limit="noSizeLimit"
      :plan-templates="planTemplates" :selected-template-id="selectedTemplateId"
      :template-variables="templateVariables" :template-variable-values="templateVariableValues"
      :plan-steps="planSteps" :planning="planning" :plan-stream-text="planStreamText"
      :skills="skills"
      @close="showAssistant = false"
      @update:response-style="responseStyle = $event"
      @update:context-mode="contextMode = $event"
      @update:memory-mode="memoryMode = $event"
      @update:search-enabled="searchEnabled = $event"
      @copy-clipboard="copyToClipboard"
      @save-dialog="saveDialogHistory"
      @clear-dialog="clearDialog"
      @send-dialog="sendDialog"
      @do-optimize="doOptimize"
      @apply-optimize="applyOptimizeResult"
      @load-template="loadTemplate"
      @update-template-var="templateVariableValues[$event.key] = $event.value"
      @apply-template-variables="applyTemplateVariables"
      @do-plan="doPlan"
      @move-step="moveStep"
      @duplicate-step="duplicateStep"
      @remove-step="planSteps.splice($event, 1)"
      @add-step="planSteps.push({ prompt: '', negative_prompt: '', description: '', image_count: 1 })"
      @execute-plan="executePlan"
      @save-as-template="saveAsTemplate"
      @update-plan-step="updatePlanStep"
    />

    <ContextMenu :visible="contextMenu.show" :x="contextMenu.x" :y="contextMenu.y"
      :items="[{ label: '重命名', action: 'rename' }, { label: '删除', action: 'delete' }]"
      @action="(a: string) => contextMenuAction(a)" />
    <ContextMenu :visible="imageContextMenu.show" :x="imageContextMenu.x" :y="imageContextMenu.y"
      :items="contextMenuImageItems"
      @action="(a: string) => imageContextAction(a)" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { useSessionStore } from '../stores/session'
import { useProviderStore } from '../stores/provider'
import { skillApi } from '../api/skill'
import { promptApi } from '../api/prompt'
import { settingsApi } from '../api/settings'
import { sessionApi } from '../api/session'
import { useBillingStore } from '../stores/billing'
import type { Skill, DefaultModelsConfig, TaskHandle, TaskUpdateEvent, PlanStep, PlanTemplate, TemplateVariable, LamEvent } from '../types'
import { dialog } from '../composables/useDialog'
import { useSessionEvents } from '../composables/useSessionEvents'
import Lightbox from '../components/session/Lightbox.vue'
import CompareOverlay from '../components/session/CompareOverlay.vue'
import ContextMenu from '../components/session/ContextMenu.vue'
import ContextImageStrip from '../components/session/ContextImageStrip.vue'
import ComposerControls from '../components/session/ComposerControls.vue'
import MessageList from '../components/session/MessageList.vue'
import AssistantSidebar from '../components/session/AssistantSidebar.vue'
import { planTemplateApi } from '../api/planTemplate'

const store = useSessionStore()
const providerStore = useProviderStore()
const billingStore = useBillingStore()
const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)
const assistantSidebarRef = ref<InstanceType<typeof AssistantSidebar> | null>(null)
const sessions = computed(() => store.sessions)
const currentSessionId = computed(() => store.currentSessionId)
const messages = computed(() => store.messages)

const inputText = ref('')
const agentMode = ref(false)
const agentStreamState = computed(() => store.getAgentStream(currentSessionId.value || '') || null)
const agentCheckpointState = computed(() => store.getCheckpoint(currentSessionId.value || '') || null)
const timelineMessages = ref<Message[]>([])
const negativePrompt = ref('')
const imageCount = ref(1)
const customCount = ref(false)
const customCountInput = ref<HTMLInputElement | null>(null)

function downloadOne(url: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = 'image.png'
  a.target = '_blank'
  a.click()
}

function downloadAll(urls: string[]) {
  urls.forEach((url) => {
    const a = document.createElement('a')
    a.href = url
    a.download = 'image.png'
    a.target = '_blank'
    a.click()
  })
}

function downloadSelected(urls: string[]) {
  downloadAll(urls)
}

function openCustomCount() {
  customCount.value = true
  nextTick(() => {
    customCountInput.value?.focus()
  })
}

function clampCount() {
  if (imageCount.value < 1) imageCount.value = 1
  if (imageCount.value > 16) imageCount.value = 16
}
const imageWidth = ref(1024)
const imageHeight = ref(1024)
const noSizeLimit = ref(false)
const showAssistant = ref(false)
const comparingImages = ref<string[]>([])
const isRefineMode = ref(false)

interface ContextImage {
  url: string
  source: 'upload' | 'context' | 'refine'
  name: string
  preview?: string
}

const contextImageList = ref<ContextImage[]>([])
const contextImageUrls = computed(() => new Set(contextImageList.value.map(x => x.url)))

function addContextImage(url: string, source: ContextImage['source'], name: string, preview?: string) {
  if (contextImageUrls.value.has(url)) return
  contextImageList.value.push({ url, source, name, preview })
}

function removeContextImage(index: number) {
  const img = contextImageList.value[index]
  if (!img) return
  if (img.source === 'upload') {
    const idx = attachments.value.findIndex(a => a.preview === img.url)
    if (idx >= 0) attachments.value.splice(idx, 1)
  }
  contextImageList.value.splice(index, 1)
}

function clearContextImages() {
  contextImageList.value = []
}

function refreshAutoContext() {
  if (isRefineMode.value) return
  const recentUrls: string[] = []
  for (const m of messages.value) {
    if (m.message_type === 'image' && m.metadata?.image_urls) {
      for (const url of (m.metadata.image_urls as string[])) {
        if (!contextImageUrls.value.has(url)) {
          recentUrls.push(url)
        }
      }
    }
  }
  for (const url of recentUrls.slice(-4)) {
    contextImageList.value.push({ url, source: 'context', name: '已生成' })
  }
}

const activeTasks = ref<Map<string, TaskHandle>>(new Map())
const generatingText = ref('生成中...')
const optimizing = ref(false)
const planning = ref(false)
const mainTextarea = ref<HTMLTextAreaElement | null>(null)
const sessionListCollapsed = ref(false)

interface Attachment {
  name: string
  type: string
  size: number
  preview?: string
  content?: string
}

const attachments = ref<Attachment[]>([])

const dragCounterMain = ref(0)
const isDragOverMain = computed(() => dragCounterMain.value > 0)

const assistantTabs = [
  { key: 'dialog', label: '对话' },
  { key: 'optimize', label: '优化' },
  { key: 'plan', label: '规划' },
  { key: 'skill', label: '技能' },
]

const contextMode = ref<'shared' | 'current'>('shared')
const memoryMode = ref<'global' | 'session'>('global')
const responseStyle = ref<'default' | 'verbose' | 'concise'>('default')
const searchEnabled = ref(false)

const optimizeDirections = [
  { key: 'detail_enhancement', label: '细节增强', desc: '提升画面细节与清晰度' },
  { key: 'style_unification', label: '风格统一', desc: '统一画面整体风格' },
  { key: 'composition_optimization', label: '构图优化', desc: '优化画面构图与布局' },
  { key: 'color_adjustment', label: '色彩调整', desc: '优化色彩搭配与氛围' },
  { key: 'lighting_enhancement', label: '光影增强', desc: '增强光影效果与层次' },
]
const optimizeResult = ref('')

const planStrategies = [
  { key: 'parallel', label: '并发生成', desc: '批量初稿/变体，快有不确定性' },
  { key: 'iterative', label: '顺序迭代', desc: '逐步精修，上一步作参考' },
]
const selectedPlanStrategy = ref('parallel')

const planTemplates = ref<PlanTemplate[]>([])
const selectedTemplateId = ref('')
const templateVariables = ref<TemplateVariable[]>([])
const templateVariableValues = ref<Record<string, string>>({})

async function loadTemplate(id?: string) {
  if (id !== undefined) selectedTemplateId.value = id
  if (!selectedTemplateId.value) {
    templateVariables.value = []
    templateVariableValues.value = {}
    return
  }
  const template = planTemplates.value.find(t => t.id === selectedTemplateId.value)
  if (!template) return
  templateVariables.value = template.variables || []
  templateVariableValues.value = {}
  for (const v of template.variables || []) {
    templateVariableValues.value[v.key] = v.default || ''
  }
  selectedPlanStrategy.value = template.strategy
}

async function applyTemplateVariables() {
  if (!selectedTemplateId.value) return
  try {
    const { data } = await planTemplateApi.apply(selectedTemplateId.value, templateVariableValues.value)
    planSteps.value = (data.steps || []).map((s: any) => ({
      prompt: s.prompt || '',
      negative_prompt: s.negative_prompt || '',
      description: s.description || '',
      image_count: s.image_count || 1,
      image_size: s.image_size || '',
    }))
    templateVariables.value = []
    templateVariableValues.value = {}
    selectedTemplateId.value = ''
  } catch (e: any) {
    dialog.showAlert('应用模板失败: ' + (e.message || '未知错误'))
  }
}

const planSteps = ref<PlanStep[]>([])
const planStreamText = ref('')
const skills = ref<Skill[]>([])
const selectedSkillIds = computed(() => assistantSidebarRef.value?.selectedSkillIds || [])

const defaultModels = ref<DefaultModelsConfig>({
  default_optimize_provider_id: null,
  default_image_provider_id: null,
  default_plan_provider_id: null,
  default_image_width: 1024,
  default_image_height: 1024,
  max_concurrent: 5,
})

const contextMenu = ref({ show: false, x: 0, y: 0, sessionId: null as string | null })
const imageContextMenu = ref({ show: false, x: 0, y: 0, url: '' })
let contextMenuTimer: ReturnType<typeof setTimeout> | null = null

function isSessionBusy(sessionId: string): boolean {
  const stream = store.getAgentStream(sessionId)
  if (stream && (stream.status === 'done' || stream.status === 'error' || stream.status === 'cancelled')) return false
  const task = activeTasks.value.get(sessionId)
  return task?.status === 'running'
}

function getSessionStatus(sessionId: string): string {
  const task = activeTasks.value.get(sessionId)
  if (task?.status === 'running') return task.type
  if (task?.status === 'error') return 'error'
  return 'idle'
}

function getTaskProgress(sessionId: string): string {
  const task = activeTasks.value.get(sessionId)
  if (!task || task.status !== 'running' || !task.total) return ''
  return `${task.progress}/${task.total}`
}

function hasCheckpointPending(sessionId: string): boolean {
  return store.getCheckpoint(sessionId)?.visible === true
}

const TASK_TYPE_LABELS: Record<string, string> = {
  single: '单图生成',
  multi_independent: '多图并行',
  iterative: '迭代精修',
  radiate: '套图辐射',
}

const currentTaskLabel = computed(() => {
  if (!currentSessionId.value) return ''
  const task = activeTasks.value.get(currentSessionId.value)
  if (!task || task.status !== 'running') return ''
  if (task.taskType) return TASK_TYPE_LABELS[task.taskType] || task.taskType
  return ''
})

const { connect: connectEvents, disconnect: disconnectEvents } = useSessionEvents(
  (event: TaskUpdateEvent) => {
    const task = activeTasks.value.get(event.session_id)
    if (task) {
      task.progress = event.progress
      task.total = event.total
      if (event.task_type) task.taskType = event.task_type
      if (event.strategy) task.strategy = event.strategy
      if (event.status === 'idle' || event.status === 'error') {
        task.status = event.status === 'error' ? 'error' : 'done'
        setTimeout(() => activeTasks.value.delete(event.session_id), 3000)
      }
    }
    if (event.message) {
      generatingText.value = event.message
    }
    if (event.progress !== undefined && event.total !== undefined && event.total > 0) {
      generatingText.value = event.message || generatingText.value
    }
    store.fetchSessions()
  },
  (tasks) => {
    for (const [sid, info] of Object.entries(tasks)) {
      if (info.status !== 'idle') {
        activeTasks.value.set(sid, {
          sessionId: sid,
          type: info.status as TaskHandle['type'],
          status: 'running',
          progress: info.progress,
          total: info.total,
          abortController: null,
        })
      }
    }
  },
  (event: LamEvent) => {
    const eventSid = event.payload?.session_id || ''
    switch (event.payload.type) {
      case 'task_started':
        store.handleAgentStarted(eventSid, event)
        break
      case 'agent_token':
        store.handleAgentToken(eventSid, event)
        break
      case 'agent_tool_call':
        store.handleToolCall(eventSid, event)
        break
      case 'agent_tool_result':
        store.handleToolResult(eventSid, event)
        break
      case 'agent_node_progress':
        store.handleNodeProgress(eventSid, event)
        break
      case 'agent_tool_warning':
        store.handleToolWarning(eventSid, event)
        break
      case 'agent_done':
        store.handleAgentDone(eventSid, event)
        activeTasks.value.delete(eventSid)
        generatingText.value = ''
        break
      case 'agent_error':
        store.handleAgentError(eventSid, event)
        activeTasks.value.delete(eventSid)
        generatingText.value = ''
        break
      case 'agent_cancelled':
        store.handleAgentCancelled(eventSid, event)
        activeTasks.value.delete(eventSid)
        generatingText.value = ''
        break
      case 'agent_checkpoint':
        store.handleCheckpoint(eventSid, event)
        break
    }
    if (event.event_type === 'task_completed' || event.event_type === 'task_failed') {
      store.handleTaskCompleted(eventSid)
      activeTasks.value.delete(eventSid)
      generatingText.value = ''
    }
  },
)

onMounted(async () => {
  connectEvents(currentSessionId.value || undefined)
  await store.fetchSessions()
  if (sessions.value.length) {
    await store.selectSession(sessions.value[0].id)
  } else {
    await store.createSession()
  }
  try {
    const { data } = await skillApi.list()
    skills.value = data
  } catch { /* ignore */ }
  try {
    const { data } = await settingsApi.getDefaultModels()
    defaultModels.value = data
    if (data.default_image_width) imageWidth.value = data.default_image_width
    if (data.default_image_height) imageHeight.value = data.default_image_height
  } catch { /* ignore */ }
  await providerStore.fetchProviders()
    try {
      const { data } = await planTemplateApi.list()
      planTemplates.value = data
    } catch { /* ignore */ }
  })

let streamAbortController: AbortController | null = null

onUnmounted(() => {
  disconnectEvents()
  if (streamAbortController) {
    streamAbortController.abort()
    streamAbortController = null
  }
  if (contextMenuTimer) clearTimeout(contextMenuTimer)
})

watch(messages, () => {
  refreshAutoContext()
})


function formatTokens(tokens: number) {
  if (tokens >= 1000) return (tokens / 1000).toFixed(1) + 'k tok'
  return tokens + ' tok'
}

async function handleFileUpload(event: Event, _type: 'image' | 'doc') {
  const input = event.target as HTMLInputElement
  if (!input.files) return
  await processMainFiles(input.files)
  input.value = ''
}

function onDragEnterMain(_e: DragEvent) {
  dragCounterMain.value++
}

function onDragOverMain(e: DragEvent) {
  e.dataTransfer!.dropEffect = 'copy'
}

function onDragLeaveMain(_e: DragEvent) {
  dragCounterMain.value--
}

async function onDropMain(e: DragEvent) {
  dragCounterMain.value = 0
  const files = e.dataTransfer?.files
  if (!files || !files.length) return
  await processMainFiles(files)
}

async function processMainFiles(files: FileList) {
  for (const file of files) {
    const attachment: Attachment = {
      name: file.name,
      type: file.type,
      size: file.size,
    }
    if (file.type.startsWith('image/')) {
      attachment.preview = await readFileAsDataURL(file)
      addContextImage(attachment.preview, 'upload', file.name, attachment.preview)
    } else if (file.name.match(/\.(txt|md|pdf|doc|docx)$/i) || file.type === 'text/plain') {
      attachment.content = await readFileAsText(file)
    }
    attachments.value.push(attachment)
  }
}

function readFileAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsText(file)
  })
}

function autoResizeTextarea() {
  const textarea = mainTextarea.value
  if (!textarea) return
  textarea.style.height = 'auto'
  const newHeight = Math.min(textarea.scrollHeight, 200)
  textarea.style.height = newHeight + 'px'
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).catch(() => {
    const textarea = document.createElement('textarea')
    textarea.value = text
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  })
}

interface MsgLike {
  content: string
  message_type?: string
  metadata?: Record<string, unknown>
}

function getMessageCopyText(msg: MsgLike): string {
  let text = msg.content || ''
  const meta = msg.metadata
  if (!meta) return text

  if (msg.message_type === 'image' && Array.isArray(meta.image_urls) && meta.image_urls.length) {
    text += '\n\n' + (meta.image_urls as string[]).map((u, i) => `[图${i + 1}] ${u}`).join('\n')
  }
  if (msg.message_type === 'optimization') {
    if (meta.original) text += `\n\n原始:\n${meta.original}`
    if (meta.optimized) text += `\n\n优化后:\n${meta.optimized}`
  }
  if ((msg.message_type === 'plan' || msg.message_type === 'agent') && Array.isArray(meta.steps)) {
    const steps = (meta.steps as Array<Record<string, unknown>>).map((s, i) => {
      const desc = (s.description || s.prompt || s.name || '') as string
      return `${i + 1}. ${desc}${s.content ? ': ' + s.content : ''}`
    }).join('\n')
    text += '\n\n' + steps
  }
  return text
}

function copyMessageContent(msg: MsgLike) {
  copyToClipboard(getMessageCopyText(msg))
}

function saveDialogHistory() {
  const msgs = assistantSidebarRef.value?.dialogMessages
  if (!msgs || !msgs.length) return
  const history = msgs.map(m => {
    const role = m.role === 'user' ? '用户' : '助手'
    return `[${role}]\n${m.content}`
  }).join('\n\n---\n\n')
  const blob = new Blob([history], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `对话记录_${new Date().toISOString().slice(0, 10)}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

async function clearDialog() {
  if (await dialog.showConfirm('确定要清除当前对话吗？建议先保存对话记录。')) {
    assistantSidebarRef.value?.clearDialog()
  }
}

async function newSession() {
  inputText.value = ''
  negativePrompt.value = ''
  attachments.value = []
  clearContextImages()
  imageCount.value = 1
  imageWidth.value = 1024
  imageHeight.value = 1024
  noSizeLimit.value = false
  optimizeResult.value = ''
  await store.createSession()
}

async function selectSession(id: string) {
  await store.selectSession(id)
  clearContextImages()
  timelineMessages.value = []
  inputText.value = ''
  negativePrompt.value = ''
  attachments.value = []
  imageCount.value = 1
  imageWidth.value = 1024
  imageHeight.value = 1024
  noSizeLimit.value = false
  optimizeResult.value = ''
  if (memoryMode.value === 'session') {
    assistantSidebarRef.value?.clearDialog()
  }
  refreshAutoContext()
  disconnectEvents()
  connectEvents(id)
}

async function cancelAgent() {
  const sid = currentSessionId.value
  if (!sid) return
  try {
    await sessionApi.cancel(sid)
    generatingText.value = '已取消'
  } catch (e: any) {
    console.error('Cancel failed:', e)
  }
}

async function resolveAgentCheckpoint(action: string) {
  const sid = currentSessionId.value
  if (!sid) return
  try {
    await sessionApi.checkpoint(sid, action)
  } catch (e: any) {
    console.error('Checkpoint resolve failed:', e)
  }
  store.clearCheckpoint(sid)
}

async function sendGenerate() {
  if (!inputText.value.trim() && !contextImageList.value.length) return
  const sid = currentSessionId.value
  if (!sid || isSessionBusy(sid)) return

  console.log('[send] agentMode:', agentMode.value, 'sid:', sid?.slice(0,8), 'prompt:', inputText.value?.slice(0,30))

  const userMessageText = inputText.value.trim()
  if (userMessageText) {
    store.messages.push({
      id: `local-${Date.now()}`,
      session_id: sid,
      role: 'user',
      content: userMessageText,
      message_type: 'text',
      metadata: {},
      created_at: new Date().toISOString(),
    })
  }

  if (agentMode.value) {
    store.handleAgentStarted(sid, { event_type: 'task_started', event_id: '', timestamp: Date.now(), source_product: '', target_product: null, correlation_id: '', payload: { type: 'task_started', session_id: sid } } as LamEvent)
  }

  const abortController = new AbortController()
  activeTasks.value.set(sid, {
    sessionId: sid,
    type: 'generate',
    status: 'running',
    progress: 0,
    total: imageCount.value,
    abortController,
  })
  generatingText.value = agentMode.value ? 'Agent 分析中...' : '生成中...'

  let promptWithContext = inputText.value
  const referenceImages: string[] = []

  const uploadImages = contextImageList.value.filter(x => x.source === 'upload')
  if (uploadImages.length) {
    const labelLines = uploadImages.map((img, i) => `[图${i + 1}: ${img.name}]`).join('\n')
    promptWithContext = labelLines + '\n' + promptWithContext
    for (const img of uploadImages) {
      if (img.preview) referenceImages.push(img.preview)
      else if (img.url.startsWith('data:')) referenceImages.push(img.url)
    }
  }

  const refineImages = contextImageList.value.filter(x => x.source === 'refine')
  if (refineImages.length) {
    const labelLines = refineImages.map((img, i) => `[图${uploadImages.length + i + 1}: ${img.name}]`).join('\n')
    promptWithContext = labelLines + '\n' + promptWithContext
    for (const img of refineImages) {
      const base64 = await fetchImageAsBase64(img.url)
      if (base64) referenceImages.push(base64)
    }
  }

  const docs = attachments.value.filter(a => !a.type.startsWith('image/') && a.content)
  if (docs.length) {
    const docContexts = docs.map(a => `\n[文档内容: ${a.name}]\n${a.content}`).join('\n')
    promptWithContext = promptWithContext + '\n' + docContexts
  }

  const recentImageUrls: string[] = []
  for (let i = messages.value.length - 1; i >= 0 && recentImageUrls.length < 4; i--) {
    const m = messages.value[i]
    if (m.message_type === 'image' && m.metadata?.image_urls && Array.isArray(m.metadata.image_urls)) {
      for (const url of (m.metadata.image_urls as string[])) {
        if (!recentImageUrls.includes(url)) {
          recentImageUrls.push(url)
          if (recentImageUrls.length >= 4) break
        }
      }
    } else if (m.message_type === 'agent' && m.metadata?.images && Array.isArray(m.metadata.images)) {
      for (const url of (m.metadata.images as string[])) {
        if (!recentImageUrls.includes(url) && typeof url === 'string' && url.startsWith('http')) {
          recentImageUrls.push(url)
          if (recentImageUrls.length >= 4) break
        }
      }
    }
  }

  const contextMessages = messages.value.slice(-10).map(m => {
    const entry: { role: string; content: string; image_urls?: string[] } = {
      role: m.role,
      content: m.content,
    }
    if (m.message_type === 'image' && m.metadata?.image_urls && Array.isArray(m.metadata.image_urls)) {
      const urls = (m.metadata.image_urls as string[]).filter((url: string) =>
        recentImageUrls.includes(url)
      )
      if (urls.length) {
        entry.image_urls = urls
      }
    }
    if (m.message_type === 'agent' && m.metadata?.images && Array.isArray(m.metadata.images)) {
      const urls = (m.metadata.images as string[]).filter((url: string) =>
        url.startsWith('http')
      )
      if (urls.length) {
        entry.image_urls = urls.slice(0, 2)
      }
    }
    return entry
  })

  const refLabels = contextImageList.value
    .filter(img => img.source !== 'context')
    .map((img, i) => ({
      index: i + 1,
      source: img.source,
      name: img.name,
    }))

  try {
    const generateData: any = {
      prompt: promptWithContext,
      negative_prompt: negativePrompt.value,
      image_count: imageCount.value,
      image_size: noSizeLimit.value ? undefined : `${imageWidth.value}x${imageHeight.value}`,
      optimize_directions: assistantSidebarRef.value?.selectedDirections.filter(d => d !== 'custom') || [],
      custom_optimize_instruction: assistantSidebarRef.value?.customInstruction || '',
      reference_images: referenceImages.length ? referenceImages : undefined,
      reference_labels: refLabels.length ? refLabels : undefined,
      context_messages: contextMessages,
      plan_strategy: '',
    }

    if (agentMode.value) {
      generateData.agent_mode = true
      generateData.agent_tools = ['web_search', 'image_search']
    }

    if (isRefineMode.value) {
      generateData.refine_mode = true
      if (refineImages.length > 0) {
        generateData.selected_image_url = refineImages[0].url
      }
    }

    await store.generate(sid, generateData)
    inputText.value = ''
    negativePrompt.value = ''
    attachments.value = []
    clearContextImages()
    if (isRefineMode.value) {
      exitRefineMode()
    }
    refreshAutoContext()
  } catch (e: any) {
    dialog.showAlert('发送失败: ' + (e.message || '未知错误'))
    console.error('sendGenerate error:', e)
  } finally {
    if (!agentMode.value) {
      const task = activeTasks.value.get(sid)
      if (task) task.status = 'done'
      setTimeout(() => activeTasks.value.delete(sid), 3000)
    }
    billingStore.fetchSummary()
  }
}

const lightboxUrl = ref('')

function openImage(url: string) {
  lightboxUrl.value = url
}

function compareSelectedImages(urls: string[]) {
  comparingImages.value = [...urls]
}

function enterRefineMode(_msg?: any, urls?: string[]) {
  isRefineMode.value = true
  clearContextImages()
  const imageUrls = urls || []
  imageUrls.forEach((url: string, i: number) => {
    addContextImage(url, 'refine', `图${i + 1}`)
  })
  inputText.value = ''
}

function exitRefineMode() {
  isRefineMode.value = false
  clearContextImages()
  refreshAutoContext()
}

async function fetchImageAsBase64(url: string): Promise<string> {
  if (url.startsWith('data:')) return url
  try {
    const resp = await fetch(url)
    if (resp.ok) {
      const blob = await resp.blob()
      return await new Promise<string>((resolve) => {
        const reader = new FileReader()
        reader.onloadend = () => resolve(reader.result as string)
        reader.readAsDataURL(blob)
      })
    }
  } catch {}
  const proxyUrl = `/api/images/proxy?url=${encodeURIComponent(url)}`
  const resp = await fetch(proxyUrl)
  if (!resp.ok) return ''
  const blob = await resp.blob()
  return await new Promise<string>((resolve) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result as string)
    reader.readAsDataURL(blob)
  })
}

function applyOptimized(text: string) {
  inputText.value = text
}

let dialogMsgId = 0

async function sendDialog() {
  const sidebar = assistantSidebarRef.value
  if (!sidebar) return
  if (!sidebar.dialogInput.trim() && !sidebar.dialogAttachments.length) return
  const userMsg = sidebar.dialogInput
  const currentAttachments = [...sidebar.dialogAttachments]
  sidebar.dialogInput = ''
  sidebar.dialogAttachments = []

  const llmProviders = providerStore.providers.filter(p => p.provider_type === 'llm' && p.is_active)
  const providerId = defaultModels.value.default_optimize_provider_id || (llmProviders.length ? llmProviders[0].id : '')

  if (!providerId) {
    sidebar.dialogMessages.push({ id: ++dialogMsgId, role: 'assistant', content: '请先在设置中配置LLM提供商' })
    return
  }

  try {
    let messageContent = userMsg
    if (currentAttachments.length) {
      const imageContexts = currentAttachments
        .filter(a => a.type.startsWith('image/'))
        .map(a => `[用户上传了图片: ${a.name}]`)
        .join('\n')
      const docContexts = currentAttachments
        .filter(a => !a.type.startsWith('image/') && a.content)
        .map(a => `\n[用户上传了文档: ${a.name}]\n${a.content}`)
        .join('\n')
      if (imageContexts) messageContent = imageContexts + '\n' + messageContent
      if (docContexts) messageContent = messageContent + '\n' + docContexts
    }

    const context = contextMode.value === 'shared' && currentSessionId.value
      ? messages.value.slice(-10).map(m => `${m.role === 'user' ? '用户' : '助手'}: ${m.content}`).join('\n') + '\n'
      : ''

    const contextImageUrls: string[] = []
    if (contextMode.value === 'shared' && currentSessionId.value) {
      for (const m of messages.value.slice(-10)) {
        if (m.metadata?.image_urls && Array.isArray(m.metadata.image_urls)) {
          for (const url of (m.metadata.image_urls as string[]).slice(0, 1)) {
            contextImageUrls.push(url)
          }
        }
      }
      contextImageUrls.splice(2)
    }

    const userMsgId = ++dialogMsgId
    sidebar.dialogMessages.push({ id: userMsgId, role: 'user', content: userMsg, attachments: currentAttachments })

    const responseHint = responseStyle.value === 'verbose'
      ? '请给出详细、全面的回答，展开解释每个要点。'
      : responseStyle.value === 'concise'
        ? '请给出极其简洁的回答，不要展开解释，直接给出核心信息。'
        : ''

    const systemPrompt = (contextMode.value === 'shared'
      ? '你是一个AI生图助手。你可以参考上下文中的对话和已生成图片来回答问题。请用中文回复。不要重复或总结上下文对话内容，直接回答用户当前问题。'
      : '你是一个AI生图助手。请根据用户输入回答问题。请用中文回复。') + responseHint

    const llmMessages: { role: string; content: string | { type: string; text?: string; image_url?: { url: string; detail: string } }[] }[] = [
      { role: 'system', content: systemPrompt },
    ]
    const history = sidebar.dialogMessages.slice(0, -1).slice(-20)
    for (const m of history) {
      llmMessages.push({ role: m.role, content: m.content })
    }
    const finalText = context + messageContent
    if (contextImageUrls.length) {
      const parts: { type: string; text?: string; image_url?: { url: string; detail: string } }[] = [
        { type: 'text', text: finalText },
      ]
      for (const url of contextImageUrls) {
        parts.push({ type: 'image_url', image_url: { url, detail: 'auto' } })
      }
      llmMessages.push({ role: 'user', content: parts } as any)
    } else {
      llmMessages.push({ role: 'user', content: finalText })
    }

    const assistantMsgId = ++dialogMsgId
    sidebar.dialogMessages.push({ id: assistantMsgId, role: 'assistant', content: '' })

    let fullContent = ''
    streamAbortController = new AbortController()
    if (searchEnabled.value) {
      sidebar.dialogToolCalls = []
      const stream = promptApi.streamChatWithTools(llmMessages, providerId, ['web_search', 'image_search'], currentSessionId.value, 0.7, streamAbortController.signal)

      for await (const event of stream) {
        if (event.type === 'token') {
          fullContent += event.data as string
          const msg = sidebar.dialogMessages.find(m => m.id === assistantMsgId)
          if (msg) msg.content = fullContent
        } else if (event.type === 'tool_call') {
          const tc = event.data as { name: string; args?: Record<string,unknown> }
          sidebar.dialogToolCalls.push({ id: crypto.randomUUID(), name: tc.name, args: tc.args, content: '', collapsed: false })
        } else if (event.type === 'tool_result') {
          const tr = event.data as { name: string; content: string; meta?: Record<string,unknown> }
          const tool = sidebar.dialogToolCalls.find(t => t.name === tr.name && !t.content)
          if (tool) tool.content = tr.content
        }
      }
    } else {
      const stream = promptApi.streamChat(llmMessages, providerId, currentSessionId.value, 0.7, streamAbortController.signal)

      for await (const token of stream) {
        fullContent += token
        const msg = sidebar.dialogMessages.find(m => m.id === assistantMsgId)
        if (msg) msg.content = fullContent
      }
    }

    streamAbortController = null

    billingStore.fetchSummary()
    await store.fetchSessions()
  } catch (e: any) {
    sidebar.dialogMessages.push({ id: ++dialogMsgId, role: 'assistant', content: '对话失败: ' + (e.message || '未知错误') })
  }
}

async function doOptimize() {
  const dirs = assistantSidebarRef.value?.selectedDirections || []
  const custom = assistantSidebarRef.value?.customInstruction || ''
  if (!inputText.value.trim() || !dirs.length || optimizing.value) return
  const sid = currentSessionId.value
  if (!sid) return
  optimizing.value = true
  optimizeResult.value = ''
  try {
    let directions = dirs.filter(d => d !== 'custom').join(',')
    if (custom) {
      directions = directions ? directions + ',custom:' + custom : 'custom:' + custom
    }
    const providerId = defaultModels.value.default_optimize_provider_id || ''
    if (!providerId) {
      const llmProviders = providerStore.providers.filter(p => p.provider_type === 'llm' && p.is_active)
      if (!llmProviders.length) {
        dialog.showAlert('请先在设置中配置LLM提供商')
        optimizing.value = false
        return
      }
      defaultModels.value.default_optimize_provider_id = llmProviders[0].id
    }

    let fullContent = ''
    streamAbortController = new AbortController()
    const stream = promptApi.optimizeStream(
      inputText.value,
      directions || 'detail_enhancement',
      defaultModels.value.default_optimize_provider_id || '',
      sid,
      streamAbortController.signal,
    )

    for await (const token of stream) {
      fullContent += token
      optimizeResult.value = fullContent
    }

    streamAbortController = null

    if (currentSessionId.value && fullContent && !fullContent.startsWith('优化失败')) {
      await sessionApi.addMessage(currentSessionId.value, {
        content: '提示词优化完成',
        message_type: 'optimization',
        metadata: { type: 'optimize', direction: directions, original: inputText.value, optimized: fullContent },
      })
    }

    billingStore.fetchSummary()
    await store.fetchSessions()
  } catch (e: any) {
    optimizeResult.value = '优化失败: ' + (e.message || '未知错误')
  } finally {
    optimizing.value = false
  }
}

function applyOptimizeResult() {
  if (optimizeResult.value && !optimizeResult.value.startsWith('优化失败')) {
    inputText.value = optimizeResult.value
  }
  optimizeResult.value = ''
}

async function doPlan() {
  if (!inputText.value.trim() || planning.value) return

  const providerId = defaultModels.value.default_plan_provider_id || ''
  if (!providerId) {
    const llmProviders = providerStore.providers.filter(p => p.provider_type === 'llm' && p.is_active)
    if (!llmProviders.length) {
      dialog.showAlert('请先在设置中配置LLM提供商')
      return
    }
    defaultModels.value.default_plan_provider_id = llmProviders[0].id
  }

  planning.value = true
  planStreamText.value = ''
  try {
    const optimizeDirs = (assistantSidebarRef.value?.selectedDirections || []).filter(d => d !== 'custom').join(', ') || '无'
    const hasRefs = attachments.value.some(a => a.type.startsWith('image/'))
    const size = noSizeLimit.value ? '不限' : `${imageWidth.value}x${imageHeight.value}`
    const strategyDesc = planStrategies.find(s => s.key === selectedPlanStrategy.value)?.desc || '并发生成'

    const systemPrompt = `你是一个AI图像生成任务规划师。根据用户的图像生成需求，将其分解为具体的子任务。

当前配置：
- 图像数量: ${imageCount.value}
- 图像尺寸: ${size}
- 优化方向: ${optimizeDirs}
- 参考图片: ${hasRefs ? '有' : '无'}
- 执行策略: ${strategyDesc}

对于每个子任务，请提供：
- prompt: 详细的图像生成提示词（英文，用于API调用）
- negative_prompt: 需要避免的元素
- description: 该步骤的中文说明
- image_count: 该步骤生成的图片数量（可选，默认为1）
- image_size: 该步骤的图片尺寸（可选，默认为${size}）

输出格式必须为JSON数组：
[
  {
    "prompt": "...",
    "negative_prompt": "...",
    "description": "...",
    "image_count": 1,
    "image_size": "${imageWidth.value}x${imageHeight.value}"
  }
]

规则：
1. prompt用英文撰写，要具体且描述性强
2. 包含风格、构图、光照和氛围细节
3. negative_prompt列出需要避免的常见问题
4. description用中文简要说明该步骤的目标
5. 将复杂需求分解为聚焦的子任务
6. ${selectedPlanStrategy.value === 'parallel' ? '各步骤应独立，可并发生成' : '后续步骤应基于前一步结果进行迭代优化'}
7. 只输出JSON数组，不要其他文字`

    let fullContent = ''
    streamAbortController = new AbortController()
    const stream = promptApi.planStream([
      { role: 'system', content: systemPrompt },
      { role: 'user', content: inputText.value },
    ], defaultModels.value.default_plan_provider_id || '', currentSessionId.value, 0.7, streamAbortController.signal)

    for await (const token of stream) {
      fullContent += token
      planStreamText.value = fullContent
    }

    streamAbortController = null

    try {
      let parsed = JSON.parse(fullContent)
      if (typeof parsed === 'object' && 'sub_tasks' in parsed) {
        parsed = parsed.sub_tasks
      }
      if (!Array.isArray(parsed)) parsed = [parsed]
      planSteps.value = parsed.map((st: any) => ({
        prompt: st.prompt || '',
        negative_prompt: st.negative_prompt || '',
        description: st.description || '',
        image_count: st.image_count || 1,
        image_size: st.image_size || '',
      })).filter((st: any) => st.prompt)
    } catch {
      planSteps.value = [{ prompt: fullContent, negative_prompt: '', description: '', image_count: 1 }]
    }

    if (planSteps.value.length === 0) {
      dialog.showAlert('规划失败：未能生成有效的步骤，请尝试更详细的描述')
    }

    if (currentSessionId.value && planSteps.value.length > 0) {
      const stepsText = planSteps.value.map((s, i) => `步骤${i + 1}: ${s.prompt}${s.negative_prompt ? '\n反向提示: ' + s.negative_prompt : ''}`).join('\n\n')
      await sessionApi.addMessage(currentSessionId.value, {
        content: `任务规划: ${inputText.value}`,
        message_type: 'plan',
        metadata: { type: 'plan', steps: planSteps.value.map((s, i) => ({ prompt: s.prompt, negative_prompt: s.negative_prompt, description: s.description })), description: inputText.value },
      })
    }

    await store.fetchSessions()
    billingStore.fetchSummary()
  } catch (e: any) {
    dialog.showAlert('规划失败: ' + (e.message || '未知错误'))
    planSteps.value = []
  } finally {
    planning.value = false
    planStreamText.value = ''
  }
}

function moveStep(index: number, direction: number) {
  const target = index + direction
  if (target < 0 || target >= planSteps.value.length) return
  const steps = [...planSteps.value]
  ;[steps[index], steps[target]] = [steps[target], steps[index]]
  planSteps.value = steps
}

function duplicateStep(index: number) {
  const step = planSteps.value[index]
  planSteps.value.splice(index + 1, 0, { ...step, description: (step.description || '') + ' (副本)' })
}

function updatePlanStep(payload: { index: number; field: string; value: any }) {
  const step = planSteps.value[payload.index]
  if (step) {
    (step as any)[payload.field] = payload.value
  }
}

async function executePlan() {
  const sid = currentSessionId.value
  if (!sid) return
  const steps = planSteps.value.filter(s => s.prompt)
  if (!steps.length) return

  const strategy = selectedPlanStrategy.value
  activeTasks.value.set(sid, {
    sessionId: sid,
    type: 'plan',
    status: 'running',
    progress: 0,
    total: steps.length,
    abortController: null,
  })
  generatingText.value = '规划执行中...'

  const initialRefs: string[] = []
  for (const img of contextImageList.value) {
    if (img.preview && img.source === 'upload') {
      initialRefs.push(img.preview)
    } else if (img.source === 'refine' || img.source === 'context') {
      const base64 = await fetchImageAsBase64(img.url)
      if (base64) initialRefs.push(base64)
    }
  }

  try {
    await sessionApi.executePlan(sid, {
      strategy,
      steps: steps.map(s => ({
        prompt: s.prompt,
        negative_prompt: s.negative_prompt,
        description: s.description,
        image_count: s.image_count || imageCount.value,
        image_size: s.image_size || (noSizeLimit.value ? '' : `${imageWidth.value}x${imageHeight.value}`),
      })),
      reference_images: initialRefs.length ? initialRefs : undefined,
      image_size: noSizeLimit.value ? '1024x1024' : `${imageWidth.value}x${imageHeight.value}`,
    })
  } catch (e: any) {
    dialog.showAlert('规划执行失败: ' + (e.message || '未知错误'))
  }

  const task = activeTasks.value.get(sid)
  if (task) task.status = 'done'
  setTimeout(() => activeTasks.value.delete(sid), 3000)
  planSteps.value = []
  billingStore.fetchSummary()
  await store.fetchSessions()
}

async function saveAsTemplate() {
  const steps = planSteps.value.filter(s => s.prompt)
  if (!steps.length) {
    dialog.showAlert('没有可保存的步骤')
    return
  }
  const name = await dialog.showPrompt('模板名称', '输入模板名称')
  if (!name) return

  // 自动扫描 {{xxx}} 变量
  const varSet = new Set<string>()
  for (const step of steps) {
    const matches = (step.prompt + ' ' + step.negative_prompt).matchAll(/\{\{(\w+)\}\}/g)
    for (const m of matches) {
      varSet.add(m[1])
    }
  }

  // 检测重复短语（出现在 2 个以上步骤中的 3 词以上短语）
  const promptWords = steps.map(s => s.prompt)
  const phraseCount: Record<string, number> = {}
  for (const p of promptWords) {
    const words = p.split(/\s+/)
    for (let len = 3; len <= Math.min(6, words.length); len++) {
      for (let i = 0; i <= words.length - len; i++) {
        const phrase = words.slice(i, i + len).join(' ')
        phraseCount[phrase] = (phraseCount[phrase] || 0) + 1
      }
    }
  }
  const repeatedPhrases = Object.entries(phraseCount)
    .filter(([, count]) => count >= 2)
    .sort((a, b) => b[0].length - a[0].length)
    .slice(0, 3)
    .map(([phrase]) => phrase)

  // 构建 variables 数组
  const variables = Array.from(varSet).map(key => ({
    key,
    type: 'string' as const,
    label: key,
    default: '',
  }))

  // 如果发现重复短语且没有已有变量覆盖，提示用户
  let description = ''
  if (repeatedPhrases.length && !varSet.size) {
    description = `检测到重复短语: ${repeatedPhrases.join(', ')}。可在模板管理中将其替换为 {{变量名}} 占位符。`
  }

  try {
    await planTemplateApi.create({
      name,
      description,
      strategy: selectedPlanStrategy.value,
      steps: steps.map(({ prompt, negative_prompt, description, image_count, image_size }) => ({
        prompt, negative_prompt, description, image_count: image_count || 1, image_size: image_size || '',
      })),
      variables,
    } as any)
    const { data } = await planTemplateApi.list()
    planTemplates.value = data
    const varMsg = variables.length ? `\n已自动识别 ${variables.length} 个变量: ${variables.map(v => '{{' + v.key + '}}').join(', ')}` : ''
    const phraseMsg = repeatedPhrases.length ? `\n检测到重复短语，建议在模板管理中替换为变量` : ''
    dialog.showAlert('模板保存成功' + varMsg + phraseMsg)
  } catch (e: any) {
    dialog.showAlert('保存失败: ' + (e.message || '未知错误'))
  }
}

function showContextMenu(e: MouseEvent, session: any) {
  if (contextMenuTimer) clearTimeout(contextMenuTimer)
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, sessionId: session.id }
  contextMenuTimer = setTimeout(() => { contextMenu.value.show = false }, 3000)
}

function showImageContextMenu(e: MouseEvent, url: string) {
  if (contextMenuTimer) clearTimeout(contextMenuTimer)
  imageContextMenu.value = { show: true, x: e.clientX, y: e.clientY, url }
  contextMenuTimer = setTimeout(() => { imageContextMenu.value.show = false }, 3000)
}

function isContextPinned(url: string): boolean {
  return contextImageUrls.value.has(url)
}

function toggleContextPin(url: string) {
  if (contextImageUrls.value.has(url)) {
    const idx = contextImageList.value.findIndex(x => x.url === url)
    if (idx >= 0) contextImageList.value.splice(idx, 1)
  } else {
    contextImageList.value.push({ url, source: 'context', name: '已固定' })
  }
  imageContextMenu.value.show = false
}

async function renameSession(id: string) {
  const title = await dialog.showPrompt('输入新名称:')
  if (title) await store.renameSession(id, title)
  contextMenu.value.show = false
}

async function deleteSession(id: string) {
  if (await dialog.showConfirm('删除此会话？')) await store.deleteSession(id)
  contextMenu.value.show = false
}

const contextMenuImageItems = computed(() => [
  { label: isContextPinned(imageContextMenu.value.url) ? '从上下文移除' : '加入上下文', action: 'toggle' },
])

function contextMenuAction(action: string) {
  if (action === 'rename') renameSession(contextMenu.value.sessionId!)
  else if (action === 'delete') deleteSession(contextMenu.value.sessionId!)
}

function imageContextAction(action: string) {
  if (action === 'toggle') toggleContextPin(imageContextMenu.value.url)
}

watch(selectedSkillIds, (ids) => {
  store.selectedSkillIds = ids
})
</script>

<style scoped>
.session-page {
  display: flex;
  height: calc(100vh - var(--topbar-height));
}

.session-list {
  width: 200px;
  border-right: 1px solid var(--border);
  background: var(--card);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.2s ease;
}

.session-list.collapsed {
  width: 40px;
}

.session-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 8px 12px;
  border-bottom: 1px solid var(--border);
  min-height: 40px;
}

.session-list.collapsed .session-list-header {
  justify-content: center;
  padding: 8px;
}

.session-list-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.session-list-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius);
  flex-shrink: 0;
}

.session-list-toggle:hover {
  background: var(--hover);
  color: var(--text);
}

.new-session-btn {
  margin: 10px 12px 8px;
  width: calc(100% - 24px);
}

.session-items {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.session-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
}

.session-item:hover {
  background: var(--hover);
}

.session-item.active {
  background: var(--active);
}

.session-item.checkpoint-pending {
  animation: checkpoint-flash 2s ease-in-out infinite;
}

@keyframes checkpoint-flash {
  0%, 100% { background: transparent; }
  50% { background: #fef3c7; }
}

.session-item.active.checkpoint-pending {
  animation: none;
  background: var(--active);
  border-left: 3px solid #d97706;
}

.session-title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.session-title-row .session-title {
  margin-bottom: 0;
  flex: 1;
  min-width: 0;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 2px;
  white-space: nowrap;
  flex-shrink: 0;
}

.status-badge.generating {
  background: #000;
  color: #fff;
}

.status-badge.optimizing,
.status-badge.planning {
  background: #E5E5E5;
  color: #000;
}

.status-badge.error {
  background: #000;
  color: #fff;
}

.status-badge.checkpoint {
  background: #d97706;
  color: #fff;
  animation: badge-pulse 1.5s ease-in-out infinite;
}

@keyframes badge-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.task-progress {
  font-size: 10px;
  color: var(--text-secondary);
}

.icon-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.session-meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-secondary);
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.input-area {
  border-top: 1px solid var(--border);
  padding: 12px 16px;
  background: var(--card);
  position: relative;
}

.input-area.drag-over {
  outline: 2px dashed var(--accent);
  outline-offset: -6px;
}

.drag-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.05);
  z-index: 10;
  pointer-events: none;
}

.drag-overlay-text {
  font-size: 14px;
  color: var(--accent);
}

.input-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-area textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  resize: none;
  font-size: 13px;
  outline: none;
  min-height: 60px;
  max-height: 200px;
  overflow-y: auto;
  transition: height 0.1s ease;
}

.input-area textarea:focus {
  border-color: var(--accent);
}

.negative-input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 12px;
  font-size: 12px;
  outline: none;
  color: var(--text-secondary);
}

.negative-input:focus {
  border-color: var(--accent);
}
</style>
