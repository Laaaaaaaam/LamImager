<template>
  <div class="reference-manage">
    <div class="page-actions">
      <button class="btn btn-primary" @click="triggerUpload">上传图片</button>
      <input ref="fileInput" type="file" accept="image/*,.txt,.md,.json" style="display: none" @change="handleUpload" />
    </div>

    <div v-if="references.length" class="ref-grid">
      <div v-for="r in references" :key="r.id" class="ref-card">
        <div class="ref-image">
          <img v-if="r.thumbnail || isImage(r.file_type)" :src="thumbnailUrl(r)" :alt="r.name" />
          <div v-else class="ref-file-icon">{{ r.file_type }}</div>
        </div>
        <div class="ref-info">
          <div class="ref-name">{{ r.name }}</div>
          <div class="ref-meta">
            <span v-if="r.is_global" class="badge badge-active">全局</span>
            <span>强度: {{ r.strength }}</span>
          </div>
          <div class="ref-controls">
            <label class="strength-label">
              强度
              <input type="range" min="0" max="1" step="0.1" :value="r.strength"
                @change="updateStrength(r.id, ($event.target as HTMLInputElement).value)" />
            </label>
            <label class="toggle-label">
              <input type="checkbox" :checked="r.is_global" @change="toggleGlobal(r)" />
              全局
            </label>
          </div>
          <button class="btn btn-sm btn-danger" @click="removeRef(r.id)">删除</button>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <p>暂无参考图</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { referenceApi } from '../api/reference'
import type { ReferenceImage } from '../types'
import { dialog } from '../composables/useDialog'

const references = ref<ReferenceImage[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(loadRefs)

async function loadRefs() {
  const { data } = await referenceApi.list()
  references.value = data
}

function triggerUpload() {
  fileInput.value?.click()
}

async function handleUpload(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files?.length) return
  const file = target.files[0]
  await referenceApi.upload(file)
  await loadRefs()
  target.value = ''
}

function isImage(fileType: string) {
  return fileType.startsWith('image/')
}

function thumbnailUrl(r: ReferenceImage) {
  if (r.thumbnail) return `/api/files/${r.thumbnail}`
  if (r.file_path) return `/api/files/${r.file_path}`
  return ''
}

async function updateStrength(id: string, value: string) {
  await referenceApi.update(id, { strength: parseFloat(value) })
}

async function toggleGlobal(r: ReferenceImage) {
  await referenceApi.update(r.id, { is_global: !r.is_global })
  await loadRefs()
}

async function removeRef(id: string) {
  if (await dialog.showConfirm('确定删除此参考图？')) {
    await referenceApi.delete(id)
    await loadRefs()
  }
}
</script>

<style scoped>
.ref-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
.ref-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.ref-image {
  height: 160px;
  background: var(--hover);
  display: flex;
  align-items: center;
  justify-content: center;
}
.ref-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.ref-file-icon {
  font-size: 12px;
  color: var(--text-secondary);
}
.ref-info {
  padding: 12px;
}
.ref-name {
  font-weight: 500;
  font-size: 13px;
  margin-bottom: 4px;
}
.ref-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.ref-controls {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}
.strength-label, .toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
.strength-label input[type="range"] {
  flex: 1;
  height: 4px;
}
</style>
