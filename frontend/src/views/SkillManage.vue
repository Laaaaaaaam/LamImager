<template>
  <div class="skill-manage">
    <div class="page-actions">
      <button class="btn btn-primary" @click="openDrawer()">创建技能</button>
    </div>

    <table v-if="skills.length">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型</th>
          <th>描述</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in skills" :key="s.id">
          <td>{{ s.name }}</td>
          <td>
            <span class="badge" :class="s.is_builtin ? 'badge-active' : 'badge-inactive'">
              {{ s.is_builtin ? '内置' : '自定义' }}
            </span>
          </td>
          <td>{{ s.description }}</td>
          <td class="actions-cell">
            <button class="btn btn-sm" @click="openDrawer(s)">编辑</button>
            <button v-if="!s.is_builtin" class="btn btn-sm btn-danger" @click="removeSkill(s.id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty-state">
      <p>暂无技能</p>
    </div>

    <div v-if="drawerOpen" class="drawer-overlay" @click.self="drawerOpen = false">
      <div class="drawer">
        <div class="drawer-header">
          <h3>{{ editingSkill ? '编辑技能' : '创建技能' }}</h3>
          <button class="btn btn-sm" @click="drawerOpen = false">关闭</button>
        </div>
        <div class="form-group">
          <label>名称</label>
          <input v-model="form.name" type="text" />
        </div>
        <div class="form-group">
          <label>描述</label>
          <textarea v-model="form.description" rows="2"></textarea>
        </div>
        <div class="form-group">
          <label>提示词模板</label>
          <textarea v-model="form.prompt_template" rows="6" placeholder="使用 {prompt} 作为用户提示词的占位符"></textarea>
        </div>
        <div class="form-group">
          <label>参数 (JSON)</label>
          <textarea v-model="paramsJson" rows="4" placeholder='{"style": "photorealistic"}'></textarea>
        </div>
        <button class="btn btn-primary" style="width: 100%" @click="saveSkill">
          {{ editingSkill ? '更新' : '创建' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { skillApi } from '../api/skill'
import type { Skill } from '../types'
import { dialog } from '../composables/useDialog'

const skills = ref<Skill[]>([])
const drawerOpen = ref(false)
const editingSkill = ref<Skill | null>(null)
const paramsJson = ref('{}')

const form = reactive({
  name: '',
  description: '',
  prompt_template: '',
})

onMounted(loadSkills)

async function loadSkills() {
  try {
    const { data } = await skillApi.list()
    skills.value = data
  } catch {
    dialog.showAlert('加载技能列表失败')
  }
}

function openDrawer(skill?: Skill) {
  editingSkill.value = skill || null
  if (skill) {
    form.name = skill.name
    form.description = skill.description
    form.prompt_template = skill.prompt_template
    paramsJson.value = JSON.stringify(skill.parameters, null, 2)
  } else {
    form.name = ''; form.description = ''; form.prompt_template = ''
    paramsJson.value = '{}'
  }
  drawerOpen.value = true
}

async function saveSkill() {
  let params = {}
  try { params = JSON.parse(paramsJson.value) } catch { dialog.showAlert('参数 JSON 格式无效'); return }

  try {
    if (editingSkill.value) {
      await skillApi.update(editingSkill.value.id, { ...form, parameters: params })
    } else {
      await skillApi.create({ ...form, parameters: params })
    }
    await loadSkills()
    drawerOpen.value = false
  } catch {
    dialog.showAlert('保存技能失败')
  }
}

async function removeSkill(id: string) {
  if (await dialog.showConfirm('确定删除此技能？')) {
    try {
      await skillApi.delete(id)
      await loadSkills()
    } catch {
      dialog.showAlert('删除技能失败')
    }
  }
}
</script>

<style scoped>
.page-actions { display: flex; justify-content: flex-end; margin-bottom: 16px; }
.actions-cell { display: flex; gap: 6px; }
</style>
