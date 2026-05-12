<template>
  <div class="compare-overlay" v-if="images.length" @click.self="$emit('close')">
    <div class="compare-view">
      <div class="compare-header">
        <span>图片对比（{{ images.length }}张）</span>
        <button class="btn btn-sm" @click="$emit('close')">关闭对比</button>
      </div>
      <div class="compare-images">
        <img v-for="(url, i) in images" :key="i" :src="url" class="compare-img" />
      </div>
      <button class="btn btn-sm" @click="$emit('download-all', images)">下载全部</button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  images: string[]
}>()

defineEmits<{
  close: []
  'download-all': [urls: string[]]
}>()
</script>

<style scoped>
.compare-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
}

.compare-view {
  background: var(--card);
  border-radius: 8px;
  padding: 24px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: auto;
}

.compare-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.compare-images {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.compare-img {
  max-width: 300px;
  max-height: 400px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}
</style>
