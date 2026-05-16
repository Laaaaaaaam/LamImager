<script setup lang="ts">
import type { CheckpointInfo } from '../../stores/session'

const props = defineProps<{
  checkpointState: CheckpointInfo
}>()

const emit = defineEmits<{
  approve: []
  retry: []
  replan: []
  cancel: []
  'open-image': [url: string]
}>()
</script>

<template>
  <div class="checkpoint-inline">
    <div class="checkpoint-info">
      <span class="checkpoint-badge">Checkpoint</span>
      <span class="checkpoint-msg">{{ checkpointState.message }}</span>
    </div>
    <div v-if="checkpointState.stepDescription" class="checkpoint-step-desc">{{ checkpointState.stepDescription }}</div>
    <div v-if="checkpointState.imageUrls?.length" class="checkpoint-images">
      <img
        v-for="(url, ci) in checkpointState.imageUrls"
        :key="ci"
        :src="url"
        class="checkpoint-thumb"
        @click="emit('open-image', url)"
      />
    </div>
    <div class="checkpoint-actions">
      <button class="cp-btn cp-approve" @click.stop="emit('approve')">继续</button>
      <button class="cp-btn cp-retry" @click.stop="emit('retry')">重做此步</button>
      <button class="cp-btn cp-replan" @click.stop="emit('replan')">重新规划</button>
      <button class="cp-btn cp-cancel" @click.stop="emit('cancel')">终止</button>
    </div>
  </div>
</template>

<style scoped>
.checkpoint-inline {
  background: #fffbeb;
  border-left: 2px solid #fde68a;
  border-radius: 0 4px 4px 0;
  padding: 6px 8px;
  margin-top: 4px;
  margin-left: 8px;
}

.checkpoint-info {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}

.checkpoint-badge {
  font-size: 9px;
  font-weight: 600;
  color: #92400e;
  background: #fef3c7;
  padding: 1px 4px;
  border-radius: 2px;
}

.checkpoint-msg {
  font-size: 11px;
  color: #92400e;
}

.checkpoint-step-desc {
  font-size: 10px;
  color: #78350f;
  margin-bottom: 4px;
}

.checkpoint-images {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.checkpoint-thumb {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 3px;
  cursor: pointer;
  border: 1px solid #e5e5e5;
  transition: opacity 0.15s;
}

.checkpoint-thumb:hover {
  opacity: 0.85;
}

.checkpoint-actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.cp-btn {
  padding: 2px 8px;
  border-radius: 2px;
  border: none;
  cursor: pointer;
  font-size: 10px;
  font-weight: 500;
  transition: opacity 0.15s;
}

.cp-btn:hover {
  opacity: 0.85;
}

.cp-approve { background: #000; color: #fff; }
.cp-retry { background: #f0a030; color: #fff; }
.cp-replan { background: #4a90d9; color: #fff; }
.cp-cancel { background: #e04040; color: #fff; }
</style>