<script setup lang="ts">
import { computed } from 'vue'
import type { AgentStreamState, AgentStreamStep } from '../../types'

const props = defineProps<{
  state: AgentStreamState
  progress?: { current: number; total: number }
}>()

defineEmits<{
  cancel: []
}>()

const statusLabel = computed(() => {
  switch (props.state.status) {
    case 'connecting': return '连接中...'
    case 'thinking': return '思考中...'
    case 'tool_running': return '执行工具...'
    case 'paused': return '已暂停'
    case 'done': return '已完成'
    case 'error': return '错误'
    default: return ''
  }
})

const isFinal = computed(() => props.state.status === 'done' || props.state.status === 'error')

function stepLabel(step: AgentStreamStep): string {
  const icon = step.type === 'tool_call' ? '>' : '<'
  if (step.status === 'done' && step.meta?.image_urls) {
    const count = (step.meta.image_urls as any[]).length
    return `${icon} ${step.name} · ${count}张`
  }
  if (step.status === 'done' && step.meta?.grid_images) {
    const count = (step.meta.grid_images as any[]).length
    return `${icon} ${step.name} · ${count}格`
  }
  if (step.name === 'generate_image' && step.args?.count) {
    const c = step.args.count as number
    const done = step.status === 'done'
    return done ? `${icon} ${step.name} · ${c}张` : `${icon} ${step.name} ×${c}`
  }
  return `${icon} ${step.name}`
}
</script>

<template>
  <div class="agent-stream-card">
    <div class="stream-header">
      <span class="agent-badge">Agent</span>
      <span class="stream-cost" v-if="state.cost !== null && state.cost !== undefined">
        费用 ¥{{ state.cost.toFixed(5) }}
      </span>
      <span class="stream-status" :class="state.status">{{ statusLabel }}</span>
      <span class="stream-progress" v-if="progress && progress.total > 0">
        {{ progress.current }}/{{ progress.total }}
      </span>
    </div>
    <div class="stream-body">
      <div class="stream-timeline" v-if="state.steps.length > 0">
        <div class="timeline-line"></div>
        <div
          v-for="step in state.steps"
          :key="step.id"
          class="timeline-node"
          :class="step.status"
        >
          <span class="node-dot"></span>
          <span class="node-label">{{ stepLabel(step) }}</span>
        </div>
      </div>
      <div class="stream-content">
        <div class="stream-text">{{ state.content }}</div>
        <span class="typing-cursor" v-if="state.status === 'thinking'"></span>
        <template v-for="step in state.steps" :key="step.id + '-img'">
          <div v-if="step.status === 'done' && step.meta?.image_urls" class="step-images">
            <img
              v-for="(url, i) in (step.meta.image_urls as string[])"
              :key="i"
              :src="url"
              class="step-thumb"
            />
          </div>
        </template>
      </div>
    </div>
    <div class="stream-footer" v-if="!isFinal">
      <button class="btn btn-danger" @click="$emit('cancel')">取消</button>
    </div>
  </div>
</template>

<style scoped>
.agent-stream-card {
  border-left: 3px solid var(--accent, #000);
  background: var(--bg, #fafafa);
  border-radius: 0 8px 8px 0;
  padding: 12px;
  margin: 8px 0;
  max-width: 100%;
}

.stream-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.agent-badge {
  background: var(--accent, #000);
  color: #fff;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  font-weight: 600;
}

.stream-cost {
  font-size: 12px;
  color: var(--text-secondary, #888);
}

.stream-status {
  font-size: 12px;
  color: var(--text-secondary, #888);
  margin-left: auto;
  transition: color 0.3s;
}
.stream-status.thinking { color: var(--accent, #000); }
.stream-status.tool_running { color: #f0a040; }
.stream-status.error { color: #e04040; }
.stream-status.done { color: #40a040; }

.stream-progress {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent, #000);
  background: #eee;
  padding: 1px 8px;
  border-radius: 8px;
}

.stream-body {
  display: flex;
  gap: 12px;
}

.stream-timeline {
  position: relative;
  width: 120px;
  flex-shrink: 0;
}

.timeline-line {
  position: absolute;
  left: 6px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: #ddd;
  transition: background 0.5s;
}

.timeline-node {
  position: relative;
  padding: 6px 0 6px 20px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.node-dot {
  position: absolute;
  left: 2px;
  top: 50%;
  transform: translateY(-50%);
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ccc;
  border: 2px solid #aaa;
  transition: all 0.3s;
}

.timeline-node.done .node-dot {
  background: var(--accent, #000);
  border-color: var(--accent, #000);
}

.timeline-node.running .node-dot {
  background: var(--accent, #000);
  border-color: var(--accent, #000);
  animation: node-pulse 0.8s ease-in-out infinite;
}

.timeline-node.error .node-dot {
  background: #e04040;
  border-color: #e04040;
}

.node-label {
  font-size: 12px;
  color: var(--text-secondary, #888);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stream-content {
  flex: 1;
  min-width: 0;
  position: relative;
}

.stream-text {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.step-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.step-thumb {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--border, #e5e5e5);
  cursor: pointer;
  transition: transform 0.15s;
}
.step-thumb:hover {
  transform: scale(1.05);
}

.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: var(--accent, #000);
  vertical-align: text-bottom;
  animation: blink-cursor 0.8s step-end infinite;
}

.stream-footer {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
}

.btn-danger {
  background: #e04040;
  color: #fff;
  border: none;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

@keyframes node-pulse {
  0%, 100% { transform: translateY(-50%) scale(1); }
  50% { transform: translateY(-50%) scale(1.4); }
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
