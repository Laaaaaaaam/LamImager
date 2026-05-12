<template>
  <div class="refine-header" v-if="isRefineMode">
    <span class="refine-label">精修模式</span>
    <button class="btn btn-sm" @click="$emit('exit-refine')">退出精修</button>
  </div>
  <div class="input-controls">
    <div class="input-options">
      <label class="upload-btn" title="上传图片">
        <input type="file" accept="image/*" multiple @change="onImageUpload" hidden />
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
      </label>
      <label class="upload-btn" title="上传文档">
        <input type="file" accept=".txt,.md,.pdf,.doc,.docx" multiple @change="onDocUpload" hidden />
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
      </label>
    </div>
    <div v-if="!agentMode" class="input-options">
      <span class="option-label">数量:</span>
      <button
        v-for="n in [1, 2, 4, 8]" :key="n"
        class="count-btn"
        :class="{ active: imageCount === n && !customCount }"
        @click="$emit('update:imageCount', n); $emit('update:customCount', false)"
      >{{ n }}</button>
      <template v-if="customCount">
        <input
          :value="imageCount"
          @input="$emit('update:imageCount', Number(($event.target as HTMLInputElement).value))"
          type="number"
          class="count-input"
          min="1"
          max="16"
          @blur="$emit('clamp-count')"
          @keyup.enter="$emit('clamp-count')"
          ref="customCountInput"
        />
      </template>
      <button
        v-else
        class="count-btn custom-toggle"
        @click="$emit('open-custom-count')"
      >+自定义</button>
      <span class="option-label size-label">尺寸:</span>
      <input
        :value="imageWidth"
        @input="$emit('update:imageWidth', Number(($event.target as HTMLInputElement).value))"
        type="number"
        class="size-input"
        :min="noSizeLimit ? undefined : 64"
        step="1"
      />
      <span class="size-sep">×</span>
      <input
        :value="imageHeight"
        @input="$emit('update:imageHeight', Number(($event.target as HTMLInputElement).value))"
        type="number"
        class="size-input"
        :min="noSizeLimit ? undefined : 64"
        step="1"
      />
      <label class="no-limit-label">
        <input type="checkbox" :checked="noSizeLimit" @change="$emit('update:noSizeLimit', ($event.target as HTMLInputElement).checked)" />
        无限制
      </label>
    </div>
    <div class="input-actions">
      <button class="btn btn-sm" @click="$emit('toggle-agent')" :class="{ 'btn-primary': agentMode }" :title="agentMode ? 'Agent 模式' : '正常模式'">
        智能
      </button>
      <button class="btn btn-sm" @click="$emit('toggle-assistant')" :class="{ 'btn-primary': showAssistant }">
        助手
      </button>
      <button class="btn btn-primary btn-sm" @click="$emit('send')" :disabled="!inputText.trim() || isBusy">
        {{ isBusy ? '任务进行中...' : (isRefineMode ? '精修发送' : (agentMode ? 'Agent发送' : '发送')) }}
      </button>
      <button
        v-if="agentMode && isBusy"
        class="btn btn-sm btn-danger"
        @click="$emit('cancel')"
      >取消</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  agentMode: boolean
  isRefineMode: boolean
  isBusy: boolean
  inputText: string
  showAssistant: boolean
  imageCount: number
  customCount: boolean
  imageWidth: number
  imageHeight: number
  noSizeLimit: boolean
}>()

const emit = defineEmits<{
  'exit-refine': []
  'toggle-agent': []
  'toggle-assistant': []
  'send': []
  'cancel': []
  'update:imageCount': [value: number]
  'update:customCount': [value: boolean]
  'update:imageWidth': [value: number]
  'update:imageHeight': [value: number]
  'update:noSizeLimit': [value: boolean]
  'open-custom-count': []
  'clamp-count': []
  'upload-image': [event: Event]
  'upload-doc': [event: Event]
}>()

const customCountInput = ref<HTMLInputElement | null>(null)

function onImageUpload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files || !input.files.length) return
  emit('upload-image', event)
  input.value = ''
}

function onDocUpload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files || !input.files.length) return
  emit('upload-doc', event)
  input.value = ''
}
</script>

<style scoped>
.refine-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  background: #f0f0f0;
  border-bottom: 1px solid var(--border);
}

.refine-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
}

.input-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.input-options {
  display: flex;
  align-items: center;
  gap: 4px;
}

.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.upload-btn:hover {
  background: var(--hover);
  color: var(--accent);
  border-color: var(--accent);
}

.option-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.count-btn {
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  font-size: 12px;
  cursor: pointer;
}

.count-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.count-btn.custom-toggle {
  font-size: 12px;
  padding: 0 6px;
  opacity: 0.7;
}

.count-input {
  width: 52px;
  height: 26px;
  padding: 0 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  text-align: center;
  font-size: 13px;
  background: var(--card);
  outline: none;
  color: var(--text);
}

.count-input:focus {
  border-color: var(--accent);
}

.size-label {
  margin-left: 8px;
}

.size-input {
  width: 60px;
  padding: 2px 4px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  text-align: center;
}

.size-input:focus {
  outline: none;
  border-color: var(--accent);
}

.size-sep {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0 2px;
}

.no-limit-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: 8px;
  cursor: pointer;
}

.no-limit-label input[type="checkbox"] {
  width: 14px;
  height: 14px;
  cursor: pointer;
}

.input-actions {
  display: flex;
  gap: 6px;
}
</style>
