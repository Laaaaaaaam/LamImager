<template>
  <div class="message-content agent">
    <button class="msg-copy-btn" @click="$emit('copy', msg)" title="复制">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
    </button>
    <div class="agent-card">
      <div class="agent-card-header">
        <span class="agent-badge">Agent</span>
        <span class="agent-cost" v-if="msg.metadata?.cost">费用 ¥{{ (msg.metadata.cost as number)?.toFixed(4) }}</span>
      </div>
      <div class="agent-card-content" v-html="renderMarkdown(msg.content)"></div>
      <div class="agent-card-images" v-if="msg.metadata?.images && (msg.metadata.images as any[]).length">
        <img
          v-for="(url, i) in (msg.metadata.images as any[])"
          :key="i"
          :src="url"
          class="agent-card-thumb"
          @click="$emit('open-image', url)"
        />
      </div>
      <div v-if="msg.metadata?.steps && (msg.metadata.steps as any[]).length" class="agent-steps-v2">
        <div
          v-for="(step, si) in msg.metadata.steps"
          :key="si"
          class="step-card"
          :class="{ expanded: expandedStepIds.has(msg.id + '-' + si) }"
          @click="toggleStep(msg.id, si)"
        >
          <div class="step-card-row">
            <span class="step-card-icon">{{ stepIcon(step) }}</span>
            <span class="step-card-name">{{ step.name }}</span>
            <span class="step-card-detail" v-if="step.args?.count > 1">×{{ step.args.count }}</span>
            <span class="step-card-result" v-if="step.type === 'tool_result'">
              <template v-if="step.meta?.image_urls">· {{ (step.meta.image_urls as any[]).length }}张</template>
              <template v-else>✓</template>
            </span>
          </div>
          <div class="step-card-body" v-if="expandedStepIds.has(msg.id + '-' + si) && (step.content || step.args)">
            <div v-if="step.args" class="step-card-args">
              <span v-for="(v, k) in step.args" :key="k" class="step-arg">{{ k }}: {{ typeof v === 'object' ? JSON.stringify(v) : v }}</span>
            </div>
            <div v-if="step.content" class="step-card-content">{{ step.content }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { renderMarkdown } from '../../composables/useMarkdown'
import type { Message } from '../../types'

defineProps<{
  msg: Message
}>()

defineEmits<{
  copy: [msg: Message]
  'open-image': [url: string]
}>()

const expandedStepIds = ref(new Set<string>())

function stepIcon(step: any): string {
  const icons: Record<string, string> = {
    web_search: '搜',
    image_search: '图',
    generate_image: '画',
    plan: '策',
  }
  return icons[step.name] || '○'
}

function toggleStep(msgId: number, stepIndex: number) {
  const key = msgId + '-' + stepIndex
  if (expandedStepIds.value.has(key)) {
    expandedStepIds.value.delete(key)
  } else {
    expandedStepIds.value.add(key)
  }
}
</script>

<style scoped>
.message-content {
  position: relative;
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;
}

.message-content.agent {
  background: var(--card);
  border: 1px solid var(--border);
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

.agent-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.agent-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: var(--hover);
}

.agent-badge {
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: #000;
  padding: 1px 8px;
  border-radius: 3px;
}

.agent-cost {
  font-size: 11px;
  color: var(--text-secondary);
}

.agent-card-content {
  padding: 8px 12px;
}

.agent-card-images {
  display: flex;
  gap: 6px;
  padding: 4px 12px 8px;
  flex-wrap: wrap;
}

.agent-card-thumb {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: var(--radius);
  cursor: pointer;
  border: 1px solid var(--border);
}

.agent-steps-v2 {
  padding: 4px 12px 8px;
}

.step-card {
  padding: 4px 8px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 12px;
  border: 1px solid transparent;
}

.step-card:hover {
  background: var(--hover);
}

.step-card.expanded {
  background: var(--hover);
  border-color: var(--border);
}

.step-card-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.step-card-icon {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-card-name {
  font-weight: 500;
}

.step-card-detail {
  color: var(--text-secondary);
  font-size: 11px;
}

.step-card-result {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-secondary);
}

.step-card-body {
  margin-top: 4px;
  padding-left: 24px;
}

.step-card-args {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.step-arg {
  font-size: 10px;
  padding: 1px 4px;
  background: var(--border);
  border-radius: 2px;
}

.step-card-content {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
  max-height: 120px;
  overflow: auto;
}
</style>
