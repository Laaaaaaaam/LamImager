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

const NODE_LABELS: Record<string, string> = {
  intent: '解析意图',
  skill_matcher: '匹配技能',
  skill: '加载偏置',
  context: '整理上下文',
  planner: '生成计划',
  prompt_builder: '优化提示词',
  executor: '执行计划',
  critic: '评估结果',
  decision: '决策',
}

const TASK_TYPE_LABELS: Record<string, string> = {
  single: '单图',
  multi_independent: '多图并行',
  iterative: '迭代精修',
  radiate: '辐射套图',
}

const STRATEGY_LABELS: Record<string, string> = {
  single: '单图',
  parallel: '并行',
  iterative: '迭代',
  radiate: '辐射',
}

const isRunning = computed(() => props.step.status === 'running')
const isDone = computed(() => props.step.status === 'done')
const isError = computed(() => props.step.status === 'error')
const isKey = computed(() => props.step.group === 'key')
const isInternal = computed(() => props.step.group === 'internal')

const label = computed(() => {
  const base = NODE_LABELS[props.step.name] || props.step.name
  if (isIntentStep.value) {
    const tt = TASK_TYPE_LABELS[props.step.meta!.task_type as string] || (props.step.meta!.task_type as string)
    const conf = Math.round((props.step.meta!.confidence as number) * 100)
    return `${base} · ${tt} (${conf}%)`
  }
  if (isPlannerStep.value) {
    const strat = STRATEGY_LABELS[props.step.meta!.strategy as string] || (props.step.meta!.strategy as string)
    const count = (props.step.meta!.steps as any[]).length
    return `${base} · ${strat}, ${count}步`
  }
  if (isExecutorStep.value && Array.isArray(props.step.meta?.completed_steps)) {
    const completed = props.step.meta!.completed_steps as any[]
    const total = completed.length > 0 ? completed[completed.length - 1].step_total || completed.length : completed.length
    const images = completed.reduce((n: number, cs: any) => n + ((cs.image_urls as any[])?.length || 0), 0)
    let info = `${completed.length}/${total}步`
    if (images > 0) info += `, ${images}张`
    return `${base} · ${info}`
  }
  if (props.step.content) return `${base} · ${props.step.content}`
  return base
})

const isIntentStep = computed(() => props.step.name === 'intent' && props.step.meta?.task_type)
const isPlannerStep = computed(() => props.step.name === 'planner' && Array.isArray(props.step.meta?.steps))
const isExecutorStep = computed(() => props.step.name === 'executor')
const hasExpandableContent = computed(() => {
  if (isIntentStep.value || isPlannerStep.value) return true
  if (isExecutorStep.value && Array.isArray(props.step.meta?.completed_steps) && (props.step.meta!.completed_steps as any[]).length > 0) return true
  if (props.step.meta?.image_urls && (props.step.meta.image_urls as any[]).length > 0) return true
  if (props.step.content && props.step.name !== 'intent' && props.step.name !== 'planner' && props.step.name !== 'executor') return true
  return false
})

const collapsedImages = computed(() => {
  if (isExecutorStep.value && Array.isArray(props.step.meta?.completed_steps)) {
    const steps = props.step.meta!.completed_steps as any[]
    const allUrls: string[] = []
    for (const cs of steps) {
      if (cs.image_urls) allUrls.push(...cs.image_urls)
    }
    const max = 4
    return { urls: allUrls.slice(0, max), hidden: Math.max(0, allUrls.length - max) }
  }
  if (props.step.meta?.image_urls?.length) {
    const all = props.step.meta.image_urls as string[]
    const max = 4
    return { urls: all.slice(0, max), hidden: Math.max(0, all.length - max) }
  }
  return { urls: [] as string[], hidden: 0 }
})

function toggleExpand() {
  if (!hasExpandableContent.value) return
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
  <div class="inline-step" :class="[step.status, step.group, { expanded: expanded || (readonly && hasExpandableContent) }]" @click="toggleExpand">
    <div class="step-row">
      <span v-if="isRunning" class="step-spinner">⠋</span>
      <span v-else-if="isDone" class="step-arrow">{{ (expanded || (readonly && hasExpandableContent)) ? '▾' : '▸' }}</span>
      <span v-else-if="isError" class="step-error-icon">✕</span>
      <span class="step-label" :class="{ dim: isInternal && isDone }">{{ label }}</span>
      <div v-if="!expanded && !(readonly && hasExpandableContent) && collapsedImages.urls.length > 0" class="step-thumbs">
        <img v-for="(url, i) in collapsedImages.urls" :key="i" :src="url" class="thumb" @click.stop="emit('open-image', url)" />
        <span v-if="collapsedImages.hidden > 0" class="thumb-more">+{{ collapsedImages.hidden }}</span>
      </div>
    </div>
    <div v-if="(expanded || (readonly && hasExpandableContent)) && hasExpandableContent" class="step-detail">
      <template v-if="isIntentStep">
        <div class="intent-card">
          <div class="intent-row">
            <span class="intent-tag" :class="step.meta!.task_type">{{ TASK_TYPE_LABELS[step.meta!.task_type as string] || step.meta!.task_type }}</span>
            <span class="intent-confidence">{{ Math.round((step.meta!.confidence as number) * 100) }}%</span>
          </div>
          <div v-if="step.meta!.reason" class="intent-reason">{{ step.meta!.reason }}</div>
        </div>
      </template>
      <template v-else-if="isPlannerStep">
        <div class="planner-card">
          <div class="planner-strategy">
            <span class="strategy-tag" :class="step.meta!.strategy">{{ STRATEGY_LABELS[step.meta!.strategy as string] || step.meta!.strategy }}</span>
          </div>
          <div class="plan-step-list">
            <div v-for="ps in (step.meta!.steps as any[])" :key="ps.index" class="plan-step-item">
              <div class="plan-step-header">
                <span class="plan-step-index">Step {{ ps.index + 1 }}</span>
                <span v-if="ps.image_count > 1" class="plan-step-count">{{ ps.image_count }}张</span>
                <span v-if="ps.checkpoint?.enabled" class="plan-step-checkpoint">Checkpoint</span>
              </div>
              <div v-if="ps.description" class="plan-step-desc">{{ ps.description }}</div>
              <div class="plan-step-prompt">{{ ps.prompt }}</div>
            </div>
          </div>
        </div>
      </template>
      <template v-else-if="isExecutorStep && Array.isArray(step.meta?.completed_steps) && (step.meta!.completed_steps as any[]).length > 0">
        <div class="executor-card">
          <div v-for="(cs, i) in (step.meta!.completed_steps as any[])" :key="i" class="exec-step-item">
            <div class="exec-step-header">
              <span class="exec-step-index">Step {{ (cs.step_index as number) + 1 }}</span>
              <span v-if="cs.tokens_in || cs.tokens_out" class="exec-step-tokens">{{ cs.tokens_in }}→{{ cs.tokens_out }} tokens</span>
              <span v-if="cs.cost" class="exec-step-cost">¥{{ (cs.cost as number).toFixed(4) }}</span>
            </div>
            <div v-if="cs.step_description" class="exec-step-desc">{{ cs.step_description }}</div>
            <div v-if="cs.step_prompt" class="exec-step-prompt">{{ cs.step_prompt }}</div>
            <div v-if="cs.image_urls && (cs.image_urls as any[]).length" class="exec-step-images">
              <img v-for="(url, ui) in (cs.image_urls as any[])" :key="ui" :src="url" class="exec-thumb" @click.stop="emit('open-image', url)" />
            </div>
          </div>
        </div>
      </template>
      <template v-else-if="step.meta?.image_urls && (step.meta.image_urls as any[]).length">
        <div class="step-images">
          <img v-for="(url, i) in (step.meta.image_urls as any[])" :key="i" :src="url" class="step-thumb" @click.stop="emit('open-image', url)" />
        </div>
      </template>
      <template v-else>
        <div class="step-text">{{ step.content }}</div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.inline-step {
  padding: 2px 0;
  cursor: default;
}

.inline-step .step-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.inline-step.has-expandable-content .step-row,
.inline-step .step-row {
  cursor: pointer;
}

.inline-step:not(.has-expandable-content) .step-row {
  cursor: default;
}

.step-spinner {
  font-size: 12px;
  color: #000;
  animation: braille-spin 0.8s steps(8) infinite;
}

.step-arrow {
  font-size: 11px;
  color: #666;
}

.step-error-icon {
  font-size: 11px;
  color: #e04040;
}

.step-label {
  font-size: 12px;
  font-weight: 500;
  color: #000;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.step-label.dim {
  font-weight: 400;
  color: #999;
}

.inline-step.error .step-label {
  color: #e04040;
}

.inline-step.running .step-label {
  color: #000;
  font-weight: 500;
}

.inline-step.done .step-label {
  color: #666;
}

.inline-step.done.internal .step-label {
  color: #999;
  font-weight: 400;
}

.step-thumbs {
  display: flex;
  gap: 3px;
  margin-left: 4px;
}

.thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 2px;
  border: 1px solid #e5e5e5;
  opacity: 0.85;
  transition: opacity 0.15s;
}

.thumb:hover {
  opacity: 1;
}

.thumb-more {
  font-size: 10px;
  color: #888;
  background: #f5f5f5;
  border: 1px solid #e5e5e5;
  border-radius: 2px;
  padding: 0 4px;
  display: flex;
  align-items: center;
  height: 40px;
  white-space: nowrap;
}

.step-detail {
  margin-top: 4px;
  padding-left: 8px;
  border-left: 2px solid #000;
  background: #fafafa;
  border-radius: 0 4px 4px 0;
  padding: 6px 8px;
}

.intent-card {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.intent-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.intent-tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 2px;
  background: #000;
  color: #fff;
}

.intent-tag.single { background: #888; }
.intent-tag.multi_independent { background: #4a90d9; }
.intent-tag.iterative { background: #d97706; }
.intent-tag.radiate { background: #7c3aed; }

.intent-confidence {
  font-size: 10px;
  color: #888;
}

.intent-reason {
  font-size: 10px;
  color: #666;
  line-height: 1.3;
}

.planner-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.planner-strategy {
  margin-bottom: 2px;
}

.strategy-tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 2px;
  background: #000;
  color: #fff;
}

.strategy-tag.single { background: #888; }
.strategy-tag.parallel { background: #4a90d9; }
.strategy-tag.iterative { background: #d97706; }
.strategy-tag.radiate { background: #7c3aed; }

.plan-step-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.plan-step-item {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 3px;
  padding: 4px 6px;
}

.plan-step-header {
  display: flex;
  align-items: center;
  gap: 4px;
}

.plan-step-index {
  font-size: 10px;
  font-weight: 600;
  color: #000;
}

.plan-step-count {
  font-size: 9px;
  color: #888;
  background: #f5f5f5;
  padding: 0 4px;
  border-radius: 2px;
}

.plan-step-checkpoint {
  font-size: 9px;
  color: #d97706;
  background: #fef3c7;
  padding: 0 4px;
  border-radius: 2px;
}

.plan-step-desc {
  font-size: 10px;
  color: #666;
  margin-top: 1px;
}

.plan-step-prompt {
  font-size: 10px;
  color: #999;
  margin-top: 1px;
  line-height: 1.3;
  max-height: 36px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.executor-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.exec-step-item {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 3px;
  padding: 4px 6px;
}

.exec-step-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.exec-step-index {
  font-size: 10px;
  font-weight: 600;
  color: #000;
}

.exec-step-tokens {
  font-size: 9px;
  color: #888;
  background: #f5f5f5;
  padding: 0 4px;
  border-radius: 2px;
}

.exec-step-cost {
  font-size: 9px;
  color: #888;
}

.exec-step-desc {
  font-size: 10px;
  color: #666;
  margin-top: 2px;
}

.exec-step-prompt {
  font-size: 10px;
  color: #999;
  margin-top: 1px;
  line-height: 1.3;
  white-space: pre-wrap;
  word-break: break-word;
}

.exec-step-images {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 3px;
}

.exec-thumb {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 3px;
  border: 1px solid #e5e5e5;
  cursor: pointer;
  transition: transform 0.15s;
}

.exec-thumb:hover {
  transform: scale(1.05);
}

.step-images {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.step-thumb {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 3px;
  border: 1px solid #e5e5e5;
  cursor: pointer;
  transition: transform 0.15s;
}

.step-thumb:hover {
  transform: scale(1.05);
}

.step-text {
  font-size: 11px;
  color: #999;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.4;
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