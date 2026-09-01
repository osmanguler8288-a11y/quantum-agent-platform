<template>
  <div class="number-card">
    <div class="nc-label">{{ label }}</div>
    <div class="nc-value">
      {{ displayValue }}<span class="nc-unit">{{ unit }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ label: string; value: number; unit: string }>()

const displayValue = computed(() => {
  const v = props.value
  if (Math.abs(v) >= 100 || (Math.abs(v) < 0.01 && v !== 0)) return v.toExponential(3)
  return v.toFixed(Math.abs(v) < 1 ? 3 : 2)
})
</script>

<style scoped>
.number-card {
  background: #fafaf9;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
}

.nc-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.nc-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--orange);
}

.nc-unit {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-left: 6px;
}
</style>
