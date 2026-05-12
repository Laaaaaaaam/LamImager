<template>
  <div class="messages-container" ref="containerRef">
    <div v-for="msg in messages" :key="msg.id" class="message" :class="msg.role">
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
      <AgentMessageCard
        v-else-if="msg.message_type === 'agent'"
        :msg="msg"
        @copy="$emit('copy', $event)"
        @open-image="$emit('open-image', $event)"
      />
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
    <div v-if="isBusy" class="message assistant">
      <div class="message-content generating" v-if="!agentStreamState || agentStreamState.status === 'done'">
        <GeneratingIndicator :text="generatingText" :task-type-label="taskTypeLabel" :progress-text="progressText" />
      </div>
      <AgentStreamCard
        v-if="agentStreamState && agentStreamState.status !== 'done'"
        :state="agentStreamState"
        @cancel="$emit('cancel')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { renderMarkdown } from '../../composables/useMarkdown'
import type { Message, AgentStreamState } from '../../types'
import TextMessageCard from './TextMessageCard.vue'
import ImageMessageCard from './ImageMessageCard.vue'
import OptimizationCard from './OptimizationCard.vue'
import PlanMessageCard from './PlanMessageCard.vue'
import AgentMessageCard from './AgentMessageCard.vue'
import GeneratingIndicator from './GeneratingIndicator.vue'
import AgentStreamCard from './AgentStreamCard.vue'

defineProps<{
  messages: Message[]
  isBusy: boolean
  generatingText: string
  taskTypeLabel: string
  progressText: string
  agentStreamState: AgentStreamState | null
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
}>()

const containerRef = ref<HTMLElement | null>(null)

defineExpose({
  containerRef,
})
</script>

<style scoped>
.messages-container {
  flex: 1;
  overflow-y: auto;
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
</style>
