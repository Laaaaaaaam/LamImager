<template>
  <div class="message-content image">
    <button class="msg-copy-btn" @click="$emit('copy', msg)" title="复制">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
    </button>
    <div v-html="renderMarkdown(msg.content)"></div>
    <div class="image-grid">
      <div v-for="(url, i) in (msg.metadata?.image_urls || [])" :key="i" class="image-item">
        <img :src="url" :alt="'图片 ' + (i + 1)" @click="$emit('open-image', url)" @contextmenu.prevent="$emit('image-context', $event, url)" />
        <label class="image-check">
          <input type="checkbox" :value="url" v-model="selectedImages" />
        </label>
      </div>
    </div>
    <div class="image-actions" v-if="(msg.metadata?.image_urls || []).length">
      <button class="btn btn-sm" @click="$emit('download-selected', selectedImages)" :disabled="!selectedImages.length">
        下载选中({{ selectedImages.length }})
      </button>
      <button class="btn btn-sm" @click="$emit('download-all', msg.metadata?.image_urls || [])">全部下载</button>
      <button class="btn btn-sm" @click="$emit('compare-selected', selectedImages)" :disabled="selectedImages.length < 2">
        对比选中
      </button>
      <button class="btn btn-sm" @click="$emit('enter-refine', msg, selectedImages)" :disabled="!selectedImages.length">
        精修({{ selectedImages.length }})
      </button>
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
  'image-context': [event: MouseEvent, url: string]
  'download-selected': [urls: string[]]
  'download-all': [urls: string[]]
  'compare-selected': [urls: string[]]
  'enter-refine': [msg: Message, urls: string[]]
}>()

const selectedImages = ref<string[]>([])
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

.message-content.image {
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

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
  margin-top: 8px;
}

.image-item {
  position: relative;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
}

.image-item img {
  width: 100%;
  display: block;
  cursor: pointer;
}

.image-check {
  position: absolute;
  top: 4px;
  left: 4px;
}

.image-check input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.image-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
</style>
