<template>
  <div class="dashboard">
    <div class="stats-row">
      <div class="stat-item">
        <span class="stat-value">{{ stats.total_sessions }}</span>
        <span class="stat-label">总会话数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ stats.total_images }}</span>
        <span class="stat-label">生成图片数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ stats.total_generations }}</span>
        <span class="stat-label">生成次数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">¥{{ stats.monthly_cost.toFixed(2) }}</span>
        <span class="stat-label">累计费用</span>
      </div>
    </div>

    <div class="quick-actions">
      <router-link to="/">
        <button class="btn btn-primary">新建会话</button>
      </router-link>
      <router-link to="/api-manage">
        <button class="btn">管理 API</button>
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { dashboardApi } from '../api/dashboard'

const stats = ref({
  total_sessions: 0,
  total_images: 0,
  total_generations: 0,
  monthly_cost: 0,
})

onMounted(async () => {
  try {
    const { data } = await dashboardApi.stats()
    stats.value = data
  } catch {
    // silently fail
  }
})
</script>

<style scoped>
.stats-row {
  display: flex;
  gap: 40px;
  margin-bottom: 32px;
}
.stat-item {
  display: flex;
  flex-direction: column;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}
.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}
.quick-actions {
  display: flex;
  gap: 12px;
}
</style>
