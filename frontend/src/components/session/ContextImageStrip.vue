<template>
  <div class="refine-strip">
    <div v-for="(img, i) in images" :key="i" class="refine-strip-item">
      <div class="refine-strip-thumb-wrap">
        <img :src="img.preview || img.url" class="refine-strip-thumb" />
        <span class="refine-strip-badge">{{ i + 1 }}</span>
      </div>
      <span class="refine-strip-label">{{ img.source === 'upload' ? img.name : (img.source === 'refine' ? '精修' : '上下文') }}</span>
      <button class="attachment-remove" @click="$emit('remove', i)">x</button>
    </div>
    <label class="refine-add-btn" title="追加图片">
      <input type="file" accept="image/*" multiple @change="onFileChange" hidden />
      + 追加
    </label>
  </div>
</template>

<script setup lang="ts">
import type { ContextImage } from '../../types'

defineProps<{
  images: ContextImage[]
}>()

const emit = defineEmits<{
  remove: [index: number]
  'add-image': [files: FileList]
}>()

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files || !input.files.length) return
  emit('add-image', input.files)
  input.value = ''
}
</script>

<style scoped>
.refine-strip {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 8px;
  flex-wrap: wrap;
  min-height: 32px;
}

.refine-strip-item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.refine-strip-thumb {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: 3px;
  border: 1px solid var(--border);
}

.refine-strip-thumb-wrap {
  position: relative;
  width: 36px;
  height: 36px;
}

.refine-strip-badge {
  position: absolute;
  top: -4px;
  left: -4px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  font-size: 9px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.refine-strip-label {
  font-size: 9px;
  color: var(--text-secondary);
  max-width: 48px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: center;
}

.refine-add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px dashed var(--border);
  border-radius: 3px;
  cursor: pointer;
  font-size: 10px;
  color: var(--text-secondary);
}

.refine-add-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.attachment-remove {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--danger);
  color: white;
  border: none;
  font-size: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
