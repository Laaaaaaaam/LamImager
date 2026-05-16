<template>
  <div class="rule-manage">
    <div class="page-actions">
      <button class="btn btn-primary" @click="openDrawer()">创建规则</button>
    </div>

    <table v-if="rules.length">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型</th>
          <th>优先级</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rules" :key="r.id">
          <td>{{ r.name }}</td>
          <td>{{ ruleTypeLabel(r.rule_type) }}</td>
          <td>{{ r.priority }}</td>
          <td>
            <button class="btn btn-sm" @click="toggleActive(r)">
              {{ r.is_active ? '启用' : '停用' }}
            </button>
          </td>
          <td class="actions-cell">
            <button class="btn btn-sm" @click="openDrawer(r)">编辑</button>
            <button class="btn btn-sm btn-danger" @click="removeRule(r.id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty-state">
      <p>暂无规则</p>
    </div>

    <div v-if="drawerOpen" class="drawer-overlay" @click.self="drawerOpen = false">
      <div class="drawer">
        <div class="drawer-header">
          <h3>{{ editingRule ? '编辑规则' : '创建规则' }}</h3>
          <button class="btn btn-sm" @click="drawerOpen = false">关闭</button>
        </div>
        <div class="form-group">
          <label>名称</label>
          <input v-model="form.name" type="text" />
        </div>
        <div class="form-group">
          <label>规则类型</label>
          <select v-model="form.rule_type">
            <option value="default_params">默认参数</option>
            <option value="filter">过滤器</option>
            <option value="workflow">工作流</option>
          </select>
        </div>
        <div class="form-group">
          <label>优先级</label>
          <input v-model.number="form.priority" type="number" min="0" />
        </div>
        <div class="form-group">
          <label>配置 (JSON)</label>
          <textarea v-model="configJson" rows="6" placeholder='{"negative_keywords": ["模糊", "低质量"]}'></textarea>
        </div>
        <div class="form-group">
          <label><input v-model="form.is_active" type="checkbox" /> 启用</label>
        </div>
        <button class="btn btn-primary" style="width: 100%" @click="saveRule">
          {{ editingRule ? '更新' : '创建' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { ruleApi } from '../api/rule'
import type { Rule } from '../types'
import { dialog } from '../composables/useDialog'

const rules = ref<Rule[]>([])
const drawerOpen = ref(false)
const editingRule = ref<Rule | null>(null)
const configJson = ref('{}')

const form = reactive({
  name: '',
  rule_type: 'default_params' as 'default_params' | 'filter' | 'workflow',
  priority: 0,
  is_active: true,
})

onMounted(loadRules)

async function loadRules() {
  try {
    const { data } = await ruleApi.list()
    rules.value = data
  } catch {
    dialog.showAlert('加载规则列表失败')
  }
}

function openDrawer(rule?: Rule) {
  editingRule.value = rule || null
  if (rule) {
    form.name = rule.name
    form.rule_type = rule.rule_type
    form.priority = rule.priority
    form.is_active = rule.is_active
    configJson.value = JSON.stringify(rule.config, null, 2)
  } else {
    form.name = ''; form.rule_type = 'default_params'; form.priority = 0; form.is_active = true
    configJson.value = '{}'
  }
  drawerOpen.value = true
}

async function saveRule() {
  let config = {}
  try { config = JSON.parse(configJson.value) } catch { dialog.showAlert('配置 JSON 格式无效'); return }

  try {
    if (editingRule.value) {
      await ruleApi.update(editingRule.value.id, { ...form, config })
    } else {
      await ruleApi.create({ ...form, config })
    }
    await loadRules()
    drawerOpen.value = false
  } catch {
    dialog.showAlert('保存规则失败')
  }
}

async function toggleActive(rule: Rule) {
  try {
    await ruleApi.toggle(rule.id)
    await loadRules()
  } catch {
    dialog.showAlert('切换规则状态失败')
  }
}

async function removeRule(id: string) {
  if (await dialog.showConfirm('确定删除此规则？')) {
    try {
      await ruleApi.delete(id)
      await loadRules()
    } catch {
      dialog.showAlert('删除规则失败')
    }
  }
}

function ruleTypeLabel(type: string) {
  const map: Record<string, string> = {
    default_params: '默认参数',
    filter: '过滤器',
    workflow: '工作流',
  }
  return map[type] || type
}
</script>

<style scoped>
.page-actions { display: flex; justify-content: flex-end; margin-bottom: 16px; }
.actions-cell { display: flex; gap: 6px; }
</style>
