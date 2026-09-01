<template>
  <div class="retry">Retrying... ({{ retryCount }}/3)</div>
</template>

<script setup lang="ts">
defineProps<{ retryCount: number }>()
</script>

<style scoped>
.retry {
  color: var(--orange);
  font-size: 13px;
  font-weight: 600;
  padding: 8px 12px;
  background: var(--orange-light);
  border-radius: 8px;
}
</style>
