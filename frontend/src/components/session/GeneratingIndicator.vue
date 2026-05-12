<template>
  <div class="generating-indicator">
    <span class="dot"></span>
    <span class="dot"></span>
    <span class="dot"></span>
  </div>
  <span class="generating-text">{{ text }}</span>
  <span v-if="taskTypeLabel" class="task-type-badge">{{ taskTypeLabel }}</span>
  <span class="task-progress" v-if="progressText">{{ progressText }}</span>
</template>

<script setup lang="ts">
defineProps<{
  text: string
  taskTypeLabel: string
  progressText: string
}>()
</script>

<style scoped>
.generating-indicator {
  display: flex;
  gap: 4px;
}

.generating-indicator .dot {
  width: 6px;
  height: 6px;
  background: var(--text-secondary);
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.generating-indicator .dot:nth-child(1) {
  animation-delay: -0.32s;
}

.generating-indicator .dot:nth-child(2) {
  animation-delay: -0.16s;
}

.generating-indicator .dot:nth-child(3) {
  animation-delay: 0s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}

.generating-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.task-type-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: #000;
  border-radius: 3px;
  vertical-align: middle;
}

.task-progress {
  font-size: 10px;
  color: var(--text-secondary);
}
</style>
