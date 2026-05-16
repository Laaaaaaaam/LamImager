<template>
  <div class="reference-manage">
    <div class="page-actions">
      <button class="btn btn-primary" @click="triggerUpload">上传图片</button>
      <input ref="fileInput" type="file" accept="image/*,.txt,.md,.json" style="display: none" @change="handleUpload" />
    </div>

    <table v-if="references.length" class="data-table">
      <thead>
        <tr>
          <th>预览</th>
          <th>名称</th>
          <th>类型</th>
          <th>强度</th>
          <th>全局</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in references" :key="r.id">
          <td>
            <img v-if="r.thumbnail || isImage(r.file_type)" :src="thumbnailUrl(r)" :alt="r.name" class="ref-thumb" />
            <span v-else class="ref-file-icon">{{ r.file_type }}</span>
          </td>
          <td>{{ r.name }}</td>
          <td>{{ r.file_type }}</td>
          <td>
            <input type="range" min="0" max="1" step="0.1" :value="r.strength"
              @change="updateStrength(r.id, ($event.target as HTMLInputElement).value)" class="strength-slider" />
            <span class="strength-value">{{ r.strength }}</span>
          </td>
          <td>
            <input type="checkbox" :checked="r.is_global" @change="toggleGlobal(r)" />
          </td>
          <td>
            <button class="btn btn-sm btn-danger" @click="removeRef(r.id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

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
  try {
    const { data } = await referenceApi.list()
    references.value = data
  } catch {
    dialog.showAlert('加载参考图列表失败')
  }
}

function triggerUpload() {
  fileInput.value?.click()
}

async function handleUpload(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files?.length) return
  const file = target.files[0]
  try {
    await referenceApi.upload(file)
    await loadRefs()
  } catch {
    dialog.showAlert('上传参考图失败')
  }
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
  try {
    await referenceApi.update(id, { strength: parseFloat(value) })
  } catch {
    dialog.showAlert('更新强度失败')
  }
}

async function toggleGlobal(r: ReferenceImage) {
  try {
    await referenceApi.update(r.id, { is_global: !r.is_global })
    await loadRefs()
  } catch {
    dialog.showAlert('切换全局状态失败')
  }
}

async function removeRef(id: string) {
  if (await dialog.showConfirm('确定删除此参考图？')) {
    try {
      await referenceApi.delete(id)
      await loadRefs()
    } catch {
      dialog.showAlert('删除参考图失败')
    }
  }
}
</script>

<style scoped>
.ref-thumb {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
}

.ref-file-icon {
  font-size: 11px;
  color: var(--text-secondary);
}

.strength-slider {
  width: 80px;
  vertical-align: middle;
}

.strength-value {
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: 4px;
}
</style>
