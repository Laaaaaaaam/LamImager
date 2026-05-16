<template>
  <div class="messages-container" ref="containerRef">
    <div v-for="msg in allMessages" :key="msg.id" class="message" :class="msg.role">
      <TextMessageCard v-if="msg.message_type === 'text'" :msg="msg" @copy="$emit('copy', $event)" />
      <ImageMessageCard
        v-else-if="msg.message_type === 'image'"
        :msg="msg"
        @copy="$emit('copy', $event)"
        @open-image="$emit('open-image', $event)"
        @image-context="(e, u) => $emit('image-context', e, u)"
        @download-selected="$emit('download-selected', $event)"
        @download-all="$emit('download-all', $event)"
        @compare-selected="$emit('compare-selected', $event)"
        @enter-refine="(m, u) => $emit('enter-refine', m, u)"
      />
      <OptimizationCard
        v-else-if="msg.message_type === 'optimization'"
        :msg="msg"
        @copy="$emit('copy', $event)"
        @apply="$emit('apply-optimized', $event)"
      />
      <PlanMessageCard v-else-if="msg.message_type === 'plan'" :msg="msg" @copy="$emit('copy', $event)" />
      <template v-else-if="msg.message_type === 'agent'">
        <div class="agent-inline-steps">
          <template v-for="step in agentToSteps(msg)" :key="step.id">
            <AgentInlineStep v-if="step.type === 'node_progress'" :step="step" :readonly="true" @open-image="$emit('open-image', $event)" />
            <AgentToolCall v-else :step="step" :readonly="true" @open-image="$emit('open-image', $event)" />
          </template>
        </div>
        <div class="agent-timeline-images" v-if="getAgentImages(msg).length">
          <img
            v-for="(url, i) in getAgentImages(msg)"
            :key="i"
            :src="url"
            class="agent-timeline-thumb"
            @click="$emit('open-image', url)"
          />
        </div>
      </template>
      <div v-else-if="msg.message_type === 'error'" class="message-content error">
        <button class="msg-copy-btn" @click="$emit('copy', msg)" title="复制">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        </button>
        <div class="error-text" v-html="renderMarkdown(msg.content)"></div>
      </div>
      <div v-else class="message-content">
        <button class="msg-copy-btn" @click="$emit('copy', msg)" title="复制">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        </button>
        <div v-html="renderMarkdown(msg.content)"></div>
      </div>
    </div>
    <div v-if="isBusy && agentStreamState && !isAgentFinal" class="message assistant">
      <div class="agent-inline-steps">
        <template v-for="step in agentStreamState.steps" :key="step.id">
          <AgentInlineStep v-if="step.type === 'node_progress'" :step="step" @open-image="$emit('open-image', $event)" />
          <AgentToolCall v-else :step="step" @open-image="$emit('open-image', $event)" />
        </template>
        <AgentCheckpoint
          v-if="checkpointState?.visible"
          :checkpoint-state="checkpointState"
          @approve="$emit('checkpoint-approve')"
          @retry="$emit('checkpoint-retry')"
          @replan="$emit('checkpoint-replan')"
          @cancel="$emit('checkpoint-cancel')"
          @open-image="$emit('open-image', $event)"
        />
        <div class="agent-cancel-row">
          <button class="btn-cancel" @click="$emit('cancel')">取消</button>
        </div>
      </div>
    </div>
    <div v-if="agentStreamState && isAgentFinal" class="message assistant">
      <div class="agent-inline-steps">
        <template v-for="step in agentStreamState.steps" :key="step.id">
          <AgentInlineStep v-if="step.type === 'node_progress'" :step="step" :readonly="true" @open-image="$emit('open-image', $event)" />
          <AgentToolCall v-else :step="step" :readonly="true" @open-image="$emit('open-image', $event)" />
        </template>
        <AgentStatusLine :state="agentStreamState" />
      </div>
    </div>
    <div v-if="isBusy && !agentStreamState" class="message assistant">
      <div class="message-content generating">
        <GeneratingIndicator :text="generatingText" :task-type-label="taskTypeLabel" :progress-text="progressText" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { renderMarkdown } from '../../composables/useMarkdown'
import type { Message, AgentStreamState, AgentStreamStep } from '../../types'
import TextMessageCard from './TextMessageCard.vue'
import ImageMessageCard from './ImageMessageCard.vue'
import OptimizationCard from './OptimizationCard.vue'
import PlanMessageCard from './PlanMessageCard.vue'
import GeneratingIndicator from './GeneratingIndicator.vue'
import AgentInlineStep from './AgentInlineStep.vue'
import AgentToolCall from './AgentToolCall.vue'
import AgentCheckpoint from './AgentCheckpoint.vue'
import AgentStatusLine from './AgentStatusLine.vue'
import type { CheckpointInfo } from '../../stores/session'

const KEY_NODES = ['intent', 'planner', 'executor', 'critic', 'decision']

function stepGroup(name: string): 'key' | 'internal' {
  return KEY_NODES.includes(name) ? 'key' : 'internal'
}

const props = defineProps<{
  messages: Message[]
  isBusy: boolean
  generatingText: string
  taskTypeLabel: string
  progressText: string
  agentStreamState: AgentStreamState | null
  timelineMessages?: Message[]
  checkpointState?: CheckpointInfo
}>()

defineEmits<{
  copy: [msg: Message]
  'open-image': [url: string]
  'image-context': [event: MouseEvent, url: string]
  'download-selected': [urls: string[]]
  'download-all': [urls: string[]]
  'compare-selected': [urls: string[]]
  'enter-refine': [msg: Message, urls: string[]]
  'apply-optimized': [text: string]
  cancel: []
  'checkpoint-approve': []
  'checkpoint-retry': []
  'checkpoint-replan': []
  'checkpoint-cancel': []
}>()

const containerRef = ref<HTMLElement | null>(null)

const allMessages = computed(() => {
  const tl = props.timelineMessages || []
  if (tl.length === 0) return props.messages
  return [...props.messages, ...tl]
})

const isAgentFinal = computed(() => {
  if (!props.agentStreamState) return false
  return props.agentStreamState.status === 'done' || props.agentStreamState.status === 'error' || props.agentStreamState.status === 'cancelled'
})

function getAgentImages(msg: Message): string[] {
  const m = msg.metadata
  const imgs = (m.images || m.final_images) as string[] | undefined
  return (imgs || []).filter((u): u is string => typeof u === 'string' && (u.startsWith('http') || u.startsWith('data:')))
}

function agentToSteps(msg: Message): AgentStreamStep[] {
  const m = msg.metadata
  const steps: AgentStreamStep[] = []

  const intent = m.intent as Record<string, unknown> | undefined
  if (intent) {
    const tt = (intent.task_type as string) || 'single'
    steps.push({
      id: `${msg.id}-intent`,
      type: 'node_progress',
      name: 'intent',
      status: 'done',
      group: 'key',
      content: `${tt} 策略`,
      meta: { task_type: tt, strategy: intent.strategy || tt, confidence: intent.confidence, reason: intent.reason },
    })
  }

  const plan = m.plan as Record<string, unknown> | undefined
  if (plan) {
    const planSteps = (plan.steps as Array<Record<string, unknown>>) || []
    steps.push({
      id: `${msg.id}-planner`,
      type: 'node_progress',
      name: 'planner',
      status: 'done',
      group: 'key',
      content: `${plan.strategy || ''} 策略，${planSteps.length} 步`,
      meta: { strategy: plan.strategy, steps: planSteps.map((s, i) => ({ index: i, description: s.description || '', prompt: s.prompt || '', image_count: s.image_count || 1, checkpoint: s.checkpoint || null })) },
    })
  }

  const execSteps = m.steps as Array<Record<string, unknown>> | undefined
  if (execSteps && execSteps.length > 0) {
    const stepDesc = execSteps.map((s, i) => `步骤 ${i + 1}: ${s.status || 'done'}`).join('\n')
    steps.push({
      id: `${msg.id}-executor`,
      type: 'node_progress',
      name: 'executor',
      status: 'done',
      group: 'key',
      content: `执行 ${execSteps.length} 步\n${stepDesc}`,
      meta: { step_count: execSteps.length },
    })
  }

  const critic = m.critic as Record<string, unknown> | undefined
  if (critic) {
    const results = (critic.results as Array<Record<string, unknown>>) || []
    const avg = critic.avg_score as number | undefined
    steps.push({
      id: `${msg.id}-critic`,
      type: 'node_progress',
      name: 'critic',
      status: 'done',
      group: 'key',
      content: `平均 ${avg ?? '?'} 分，${results.length} 张图已评估`,
      meta: { avg_score: avg, reviewed: results.length },
    })
  }

  const decision = m.decision as string | undefined
  if (decision) {
    steps.push({
      id: `${msg.id}-decision`,
      type: 'node_progress',
      name: 'decision',
      status: 'done',
      group: 'key',
      content: decision === 'pass' ? `通过（评分达标）` : `重试（${decision}）`,
      meta: { result: decision },
    })
  }

  return steps
}

defineExpose({
  containerRef,
})
</script>

<style scoped>
.messages-container {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  max-width: 80%;
}

.message.user {
  align-self: flex-end;
}

.message.assistant {
  align-self: flex-start;
}

.message.assistant:has(.agent-inline-steps) {
  max-width: 95%;
}

.agent-inline-steps {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-cancel-row {
  margin-top: 6px;
  display: flex;
  justify-content: flex-end;
}

.btn-cancel {
  background: #e04040;
  color: #fff;
  border: none;
  padding: 3px 10px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 11px;
}

.message-content {
  position: relative;
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;
}

.message-content.error {
  background: #fff5f5;
  border: 1px solid #ffcdd2;
}

.error-text {
  color: #c62828;
}

.message-content.generating {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--hover);
  border-radius: 12px;
}

.msg-copy-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  background: none;
  border: none;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
  color: var(--text-secondary);
  padding: 2px;
}

.message-content:hover .msg-copy-btn {
  opacity: 1;
}

.agent-timeline-images {
  display: flex;
  gap: 6px;
  padding: 6px 0 0;
  flex-wrap: wrap;
}

.agent-timeline-thumb {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: var(--radius, 6px);
  cursor: pointer;
  border: 1px solid var(--border, #e5e5e5);
}
</style>