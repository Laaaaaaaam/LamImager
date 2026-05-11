<script setup lang="ts">
defineProps<{
  visible: boolean
  message: string
  previewUrl?: string
  toolName?: string
}>()

defineEmits<{
  approve: []
  reject: []
  skip: []
}>()
</script>

<template>
  <div v-if="visible" class="checkpoint-overlay">
    <div class="checkpoint-card">
      <h3 class="checkpoint-title">检查点</h3>
      <p class="checkpoint-tool" v-if="toolName">{{ toolName }}</p>
      <p class="checkpoint-message">{{ message }}</p>
      <img v-if="previewUrl" :src="previewUrl" class="checkpoint-preview" />
      <div class="checkpoint-actions">
        <button class="btn btn-primary" @click="$emit('approve')">继续</button>
        <button class="btn" @click="$emit('skip')">跳过</button>
        <button class="btn btn-danger" @click="$emit('reject')">终止</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.checkpoint-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
}

.checkpoint-card {
  background: #fff;
  border-radius: 8px;
  padding: 24px;
  max-width: 420px;
  width: 90%;
  text-align: center;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.checkpoint-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
}

.checkpoint-tool {
  font-size: 12px;
  color: var(--text-secondary, #888);
  margin: 0 0 8px;
}

.checkpoint-message {
  font-size: 14px;
  line-height: 1.5;
  margin: 0 0 16px;
  color: #333;
}

.checkpoint-preview {
  max-width: 100%;
  max-height: 240px;
  border-radius: 6px;
  margin-bottom: 16px;
  object-fit: contain;
}

.checkpoint-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
}

.btn {
  padding: 6px 16px;
  border-radius: 4px;
  border: 1px solid var(--border, #e5e5e5);
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}

.btn-primary {
  background: var(--accent, #000);
  color: #fff;
  border-color: var(--accent, #000);
}

.btn-danger {
  background: #e04040;
  color: #fff;
  border-color: #e04040;
}
</style>
