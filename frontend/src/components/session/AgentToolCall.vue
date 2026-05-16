<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AgentStreamStep } from '../../types'

const props = defineProps<{
  step: AgentStreamStep
  readonly?: boolean
}>()

const emit = defineEmits<{
  'open-image': [url: string]
}>()

const expanded = ref(false)

const isRunning = computed(() => props.step.status === 'running')
const isDone = computed(() => props.step.status === 'done')
const isError = computed(() => props.step.status === 'error')

const prefix = computed(() => props.step.type === 'tool_call' ? '>' : '<')

const label = computed(() => {
  const icon = props.step.type === 'tool_call' ? '>' : '<'
  if (isDone.value && props.step.meta?.image_urls) {
    const count = (props.step.meta.image_urls as any[]).length
    return `${icon} ${props.step.name} · ${count}张`
  }
  if (isDone.value && props.step.meta?.grid_images) {
    const count = (props.step.meta.grid_images as any[]).length
    return `${icon} ${props.step.name} · ${count}格`
  }
  if (props.step.name === 'generate_image' && props.step.args?.count) {
    const c = props.step.args.count as number
    return isDone.value ? `${icon} ${props.step.name} · ${c}张` : `${icon} ${props.step.name} ×${c}`
  }
  return `${icon} ${props.step.name}`
})

const hasDetail = computed(() => {
  if (props.step.args && Object.keys(props.step.args as object).length > 0) return true
  if (props.step.content) return true
  if (props.step.meta?.image_urls && (props.step.meta.image_urls as any[]).length > 0) return true
  return false
})

function toggleExpand() {
  if (!hasDetail.value) return
  expanded.value = !expanded.value
}

function formatArgValue(v: any): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'string') return v.length > 80 ? v.slice(0, 80) + '...' : v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) return v.length === 0 ? '[]' : v.map(i => formatArgValue(i)).join(', ')
  try { return JSON.stringify(v).slice(0, 120) } catch { return String(v) }
}
</script>

<template>
  <div class="tool-call" :class="[step.status, step.type]" @click="toggleExpand">
    <div class="tool-row">
      <span v-if="isRunning" class="tool-spinner">⠋</span>
      <span v-else-if="isDone" class="tool-check">✓</span>
      <span v-else-if="isError" class="tool-error-icon">✕</span>
      <span class="tool-label" :class="{ dim: isDone }">{{ label }}</span>
    </div>
    <div v-if="expanded || (readonly && hasDetail)" class="tool-detail">
      <div v-if="step.args && Object.keys(step.args as object).length > 0" class="tool-args">
        <div v-for="(v, k) in (step.args as Record<string, any>)" :key="k" class="tool-arg-row">
          <span class="tool-arg-key">{{ k }}</span>
          <span class="tool-arg-val">{{ formatArgValue(v) }}</span>
        </div>
      </div>
      <div v-if="step.content" class="tool-result">{{ step.content }}</div>
      <div v-if="step.meta?.image_urls && (step.meta.image_urls as any[]).length" class="tool-images">
        <img v-for="(url, i) in (step.meta.image_urls as any[])" :key="i" :src="url" class="tool-thumb" @click.stop="emit('open-image', url)" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-call {
  padding: 2px 0;
  cursor: pointer;
}

.tool-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tool-spinner {
  font-size: 12px;
  color: #000;
  animation: braille-spin 0.8s steps(8) infinite;
}

.tool-check {
  font-size: 11px;
  color: #666;
}

.tool-error-icon {
  font-size: 11px;
  color: #e04040;
}

.tool-label {
  font-size: 12px;
  font-weight: 400;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tool-label.dim {
  color: #999;
}

.tool-call.running .tool-label {
  color: #000;
  font-weight: 500;
}

.tool-call.error .tool-label {
  color: #e04040;
}

.tool-detail {
  margin-top: 3px;
  padding-left: 8px;
  border-left: 2px solid #e5e5e5;
  background: #fafafa;
  border-radius: 0 4px 4px 0;
  padding: 6px 8px;
}

.tool-args {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tool-arg-row {
  display: flex;
  gap: 6px;
  font-size: 10px;
}

.tool-arg-key {
  color: #888;
  min-width: 50px;
  flex-shrink: 0;
}

.tool-arg-val {
  color: #333;
  word-break: break-word;
}

.tool-result {
  font-size: 10px;
  color: #666;
  margin-top: 4px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.3;
  max-height: 120px;
  overflow-y: auto;
}

.tool-images {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 3px;
}

.tool-thumb {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 3px;
  border: 1px solid #e5e5e5;
  cursor: pointer;
  transition: transform 0.15s;
}

.tool-thumb:hover {
  transform: scale(1.05);
}

@keyframes braille-spin {
  0% { content: '⠋'; }
  12.5% { content: '⠙'; }
  25% { content: '⠹'; }
  37.5% { content: '⠸'; }
  50% { content: '⠼'; }
  62.5% { content: '⠴'; }
  75% { content: '⠦'; }
  87.5% { content: '⠧'; }
  100% { content: '⠇'; }
}
</style>