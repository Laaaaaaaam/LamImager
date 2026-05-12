<template>
  <div v-if="visible" class="context-menu" :style="{ left: x + 'px', top: y + 'px' }">
    <button v-for="item in items" :key="item.action" @click="$emit('action', item.action)">{{ item.label }}</button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  x: number
  y: number
  items: Array<{ label: string; action: string }>
}>()

defineEmits<{
  action: [action: string]
}>()
</script>

<style scoped>
.context-menu {
  position: fixed;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  z-index: 300;
  padding: 4px;
}

.context-menu button {
  display: block;
  width: 100%;
  padding: 6px 12px;
  border: none;
  background: none;
  text-align: left;
  font-size: 12px;
  cursor: pointer;
  border-radius: var(--radius);
}

.context-menu button:hover {
  background: var(--hover);
}
</style>
