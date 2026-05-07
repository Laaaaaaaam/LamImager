<template>
  <div class="app-layout">
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-brand">
        <span v-if="!sidebarCollapsed">LamImager</span>
        <button class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? '展开' : '折叠'">
          <ChevronLeft v-if="!sidebarCollapsed" :size="16" />
          <ChevronRight v-else :size="16" />
        </button>
      </div>
      <nav class="sidebar-nav">
        <router-link to="/" class="nav-item" active-class="nav-item--active">
          <MessageSquare :size="18" />
          <span v-if="!sidebarCollapsed">会话</span>
        </router-link>
        <router-link to="/api-manage" class="nav-item" active-class="nav-item--active">
          <Server :size="18" />
          <span v-if="!sidebarCollapsed">API 配置</span>
        </router-link>
        <router-link to="/skills" class="nav-item" active-class="nav-item--active">
          <Wand2 :size="18" />
          <span v-if="!sidebarCollapsed">技能</span>
        </router-link>
        <router-link to="/rules" class="nav-item" active-class="nav-item--active">
          <SlidersHorizontal :size="18" />
          <span v-if="!sidebarCollapsed">规则</span>
        </router-link>
        <router-link to="/references" class="nav-item" active-class="nav-item--active">
          <Image :size="18" />
          <span v-if="!sidebarCollapsed">参考图</span>
        </router-link>
        <router-link to="/plan-templates" class="nav-item" active-class="nav-item--active">
          <Layers :size="18" />
          <span v-if="!sidebarCollapsed">规划模板</span>
        </router-link>
        <router-link to="/settings" class="nav-item" active-class="nav-item--active">
          <SettingsIcon :size="18" />
          <span v-if="!sidebarCollapsed">设置</span>
        </router-link>
      </nav>
    </aside>
    <div class="main-area" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
      <header class="topbar">
        <h1 class="topbar-title">{{ currentPageTitle }}</h1>
        <div class="topbar-billing" @click="showBilling = !showBilling">
          本月 ¥{{ billingStore.summary.month.toFixed(2) }}
        </div>
      </header>
      <main class="content" :class="{ 'no-padding': route.name === 'sessions' }">
        <router-view />
      </main>
    </div>

    <div v-if="showBilling" class="drawer-overlay" @click.self="showBilling = false">
      <div class="drawer billing-drawer">
        <div class="drawer-header">
          <h3>账单</h3>
          <button class="btn btn-sm" @click="showBilling = false">关闭</button>
        </div>
        <div class="billing-summary-row">
          <div class="billing-stat">
            <span class="billing-value">¥{{ billingStore.summary.today.toFixed(2) }}</span>
            <span class="billing-label">今日</span>
          </div>
          <div class="billing-stat">
            <span class="billing-value">¥{{ billingStore.summary.month.toFixed(2) }}</span>
            <span class="billing-label">本月</span>
          </div>
          <div class="billing-stat">
            <span class="billing-value">¥{{ billingStore.summary.total.toFixed(2) }}</span>
            <span class="billing-label">累计</span>
          </div>
        </div>
        <div class="billing-actions">
          <button class="btn" @click="exportCsv">导出 CSV</button>
        </div>
      </div>
    </div>
  </div>
  <ConfirmDialog />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ConfirmDialog from './components/ConfirmDialog.vue'
import { useBillingStore } from './stores/billing'
import { dialog } from './composables/useDialog'
import { billingApi } from './api/billing'
import { settingsApi } from './api/settings'
import {
  MessageSquare,
  Server,
  Wand2,
  SlidersHorizontal,
  Image,
  Settings as SettingsIcon,
  ChevronLeft,
  ChevronRight,
  Layers,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const billingStore = useBillingStore()
const showBilling = ref(false)
const sidebarCollapsed = ref(false)

const pageTitles: Record<string, string> = {
  sessions: '会话',
  'api-manage': 'API 配置',
  skills: '技能',
  rules: '规则',
  references: '参考图',
  'plan-templates': '规划模板',
  settings: '设置',
}

const currentPageTitle = computed(() => pageTitles[route.name as string] || 'LamImager')

onMounted(async () => {
  billingStore.fetchSummary()

  ;(window as any).toggleAssistant = () => {
    router.push('/')
  }
  ;(window as any).navigateTo = (path: string) => {
    router.push(path)
  }

  try {
    const { data } = await settingsApi.getMigrationStatus()
    if (data.can_migrate && await dialog.showConfirm(
      '检测到网页版数据，是否导入到桌面应用？',
      '数据迁移'
    )) {
      const res = await settingsApi.importData()
      dialog.showAlert(res.data.message)
    }
  } catch { /* ignore */ }
})

onUnmounted(() => {
  delete (window as any).toggleAssistant
  delete (window as any).navigateTo
})

async function exportCsv() {
  try {
    const { data } = await billingApi.exportCsv()
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = 'billing_export.csv'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    dialog.showAlert(e.message || '导出失败')
  }
}
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: var(--sidebar-width);
  background: var(--card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 50;
  transition: width 0.2s ease;
}

.sidebar.collapsed {
  width: 44px;
}

.sidebar-brand {
  padding: 12px 14px;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.5px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 48px;
  white-space: nowrap;
  overflow: hidden;
}

.sidebar-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius);
  flex-shrink: 0;
}

.sidebar-toggle:hover {
  background: var(--hover);
  color: var(--text);
}

.sidebar-nav {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius);
  color: var(--text-secondary);
  font-size: 13px;
  transition: all 0.15s;
  white-space: nowrap;
  overflow: hidden;
}

.sidebar.collapsed .nav-item {
  justify-content: center;
  padding: 8px;
}

.nav-item:hover {
  background: var(--hover);
  color: var(--text);
}

.nav-item--active {
  background: var(--active);
  color: var(--text);
  font-weight: 500;
}

.main-area {
  margin-left: var(--sidebar-width);
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  transition: margin-left 0.2s ease;
}

.main-area.sidebar-collapsed {
  margin-left: 44px;
}

.topbar {
  height: var(--topbar-height);
  background: var(--card);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 40;
}

.topbar-title {
  font-size: 14px;
  font-weight: 600;
}

.topbar-billing {
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px 10px;
  border-radius: var(--radius);
  transition: background 0.15s;
}

.topbar-billing:hover {
  background: var(--hover);
}

.content {
  flex: 1;
  padding: 24px;
}

.content.no-padding {
  padding: 0;
}

.billing-summary-row {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
}

.billing-stat {
  display: flex;
  flex-direction: column;
}

.billing-value {
  font-size: 20px;
  font-weight: 700;
}

.billing-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.billing-drawer {
  width: 360px;
}
</style>
