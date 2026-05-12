<template>
  <div class="message-content text">
    <button class="msg-copy-btn" @click="$emit('copy', msg)" title="复制">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
    </button>
    <div v-html="renderMarkdown(msg.content)"></div>
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

.message-content.text {
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
</style>
