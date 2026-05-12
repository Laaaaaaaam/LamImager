<template>
  <div class="message-content plan">
    <button class="msg-copy-btn" @click="$emit('copy', msg)" title="复制">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
    </button>
    <div class="plan-card">
      <div class="plan-card-header" @click="toggleExpand">
        <div class="plan-card-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
          <span v-html="renderMarkdown(msg.content)"></span>
        </div>
        <div class="plan-card-meta">
          <span class="plan-step-count">{{ (msg.metadata?.steps || []).length }} 个步骤</span>
          <svg :class="['plan-chevron', { expanded: isExpanded }]" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
      </div>
      <div class="plan-card-body" v-if="isExpanded && msg.metadata?.steps">
        <div v-for="(step, i) in (msg.metadata.steps as any[])" :key="i" class="plan-card-step">
          <div class="plan-step-header">
            <span class="step-num">{{ i + 1 }}</span>
            <span class="step-prompt-preview">{{ step.description || step.prompt.slice(0, 80) }}{{ (!step.description && step.prompt.length > 80) ? '...' : '' }}</span>
          </div>
          <div class="plan-step-detail">
            <div class="step-field">
              <label>Prompt</label>
              <p>{{ step.prompt }}</p>
            </div>
            <div class="step-field" v-if="step.negative_prompt">
              <label>Negative Prompt</label>
              <p>{{ step.negative_prompt }}</p>
            </div>
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
}>()

const isExpanded = ref(false)

function toggleExpand() {
  isExpanded.value = !isExpanded.value
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

.message-content.plan {
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

.plan-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.plan-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  background: var(--hover);
}

.plan-card-header:hover {
  background: var(--border);
}

.plan-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
}

.plan-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-step-count {
  font-size: 11px;
  color: var(--text-secondary);
}

.plan-chevron {
  transition: transform 0.2s;
}

.plan-chevron.expanded {
  transform: rotate(180deg);
}

.plan-card-body {
  padding: 8px 12px;
}

.plan-card-step {
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}

.plan-card-step:last-child {
  border-bottom: none;
}

.plan-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-num {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-prompt-preview {
  font-size: 12px;
  color: var(--text-secondary);
}

.plan-step-detail {
  margin-top: 4px;
  padding-left: 28px;
}

.step-field {
  margin-bottom: 2px;
}

.step-field label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.step-field p {
  font-size: 12px;
  margin: 0;
  white-space: pre-wrap;
}
</style>
