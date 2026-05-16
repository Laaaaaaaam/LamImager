<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import type { AgentStreamState } from '../../types'

const props = defineProps<{
  state: AgentStreamState
}>()

const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  if (props.state.status !== 'done' && props.state.status !== 'error' && props.state.status !== 'cancelled') {
    timer = setInterval(() => { now.value = Date.now() }, 1000)
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const elapsed = computed(() => {
  if (!props.state.startedAt) return ''
  const end = (props.state.status === 'done' || props.state.status === 'error' || props.state.status === 'cancelled')
    ? now.value
    : now.value
  const seconds = Math.round((end - props.state.startedAt) / 1000)
  return `${seconds}s`
})

const statusText = computed(() => {
  switch (props.state.status) {
    case 'done': return ''
    case 'error': return '错误'
    case 'cancelled': return '已取消'
    case 'thinking': return '思考中...'
    case 'tool_running': return '执行工具...'
    case 'paused': return '等待确认'
    case 'connecting': return '连接中...'
    default: return ''
  }
})

const dotColor = computed(() => {
  if (props.state.status === 'error') return '#e04040'
  if (props.state.status === 'cancelled') return '#999'
  return '#000'
})
</script>

<template>
  <div class="agent-status-line">
    <span class="status-dot" :style="{ background: dotColor }"></span>
    <span class="status-label">Agent</span>
    <span v-if="state.cost !== null && state.cost !== undefined" class="status-cost">· ¥{{ state.cost.toFixed(4) }}</span>
    <span v-if="statusText" class="status-text">{{ statusText }}</span>
    <span v-if="elapsed" class="status-time">· {{ elapsed }}</span>
  </div>
</template>

<style scoped>
.agent-status-line {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 0;
  font-size: 11px;
  color: #999;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-label {
  font-weight: 500;
  color: #666;
}

.status-cost {
  color: #999;
}

.status-text {
  color: #999;
}

.status-time {
  color: #999;
}
</style>