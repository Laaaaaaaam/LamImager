<template>
  <div class="message-content optimization">
    <button class="msg-copy-btn" @click="$emit('copy', msg)" title="复制">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
    </button>
    <div v-html="renderMarkdown(msg.content)"></div>
    <div class="optimization-compare">
      <div class="compare-side">
        <div class="compare-label">原始</div>
        <div class="compare-text">{{ msg.metadata?.original }}</div>
      </div>
      <div class="compare-side">
        <div class="compare-label">优化后</div>
        <div class="compare-text optimized">{{ msg.metadata?.optimized }}</div>
      </div>
    </div>
    <button class="btn btn-sm" @click="$emit('apply', msg.metadata?.optimized || '')">应用优化</button>
    <button class="btn btn-sm" @click="$emit('apply', msg.metadata?.original || '')">使用原始</button>
  </div>
</template>

<script setup lang="ts">
import { renderMarkdown } from '../../composables/useMarkdown'
import type { Message } from '../../types'

defineProps<{
  msg: Message
}>()

defineEmits<{
  copy: [msg: Message]
  apply: [text: string]
}>()
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

.message-content.optimization {
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

.optimization-compare {
  display: flex;
  gap: 12px;
  margin: 8px 0;
}

.compare-side {
  flex: 1;
  padding: 8px;
  background: var(--hover);
  border-radius: var(--radius);
}

.compare-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.compare-text {
  font-size: 13px;
  white-space: pre-wrap;
}

.compare-text.optimized {
  color: var(--accent);
  font-weight: 500;
}
</style>
