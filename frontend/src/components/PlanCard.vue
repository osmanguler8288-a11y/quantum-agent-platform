<template>
  <div class="plan">
    <div class="label">PLAN — {{ plan.length }} steps</div>
    <div class="plan-list">
      <div v-for="(s, i) in plan" :key="i" class="plan-item" :class="{ reasoning: s.type === 'reasoning' }">
        <div class="plan-idx">{{ i + 1 }}</div>
        <div class="plan-body">
          <div class="plan-tool">
            <span class="type-badge" :class="s.type">{{ s.type === 'reasoning' ? 'LLM' : 'TOOL' }}</span>
            <span class="tool-name">{{ s.step }}</span>
            <span v-if="s.action" class="plan-action">{{ s.action }}</span>
          </div>
          <div v-if="s.type !== 'reasoning' && s.params && Object.keys(s.params).length" class="plan-params">
            <span v-for="(v, k) in s.params" :key="k" class="param-tag">{{ k }}: {{ String(v) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PlanStep } from '@/types'

defineProps<{ plan: PlanStep[] }>()
</script>

<style scoped>
.label {
  font-size: 11px;
  font-weight: 600;
  color: var(--orange);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.plan-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plan-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: #fafaf9;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.plan-item.reasoning {
  background: var(--purple-bg);
  border-color: var(--purple-border);
}

.plan-idx {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #fff7ed;
  color: var(--orange);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
  border: 1px solid var(--orange-border);
}

.plan-body {
  flex: 1;
  min-width: 0;
}

.plan-tool {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.type-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 700;
}
.type-badge.tool {
  background: var(--orange-light);
  color: var(--amber-text);
}
.type-badge.reasoning {
  background: var(--purple-bg);
  color: var(--purple-text);
}

.tool-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--orange);
}

.plan-action {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
}

.plan-params {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.param-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #fff7ed;
  color: var(--amber-text);
  font-family: 'SF Mono', 'Fira Code', monospace;
}
</style>
