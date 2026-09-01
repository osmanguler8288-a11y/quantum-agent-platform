<template>
  <div class="suggestions">
    <span v-for="s in suggestions" :key="s" class="chip" @click="$emit('select', s)">{{ s }}</span>
  </div>
</template>

<script setup lang="ts">
defineEmits<{ (e: 'select', text: string): void }>()

const suggestions = [
  '优化苯结构并用B3LYP/6-31G*计算HOMO能级',
  '算甲醇的红外光谱',
  '计算苯的吸收光谱（TD-DFT）',
  '算水分子的偶极矩',
  '搜索正丁烷的构象',
  '优化乙醇结构并计算单点能',
  '优化Ni催化剂结构并做频率分析',
]
</script>

<style scoped>
.suggestions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  max-width: 820px;
  margin: 8px auto 0;
}

.chip {
  font-size: 12px;
  padding: 6px 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
  cursor: pointer;
  color: var(--text-secondary);
  background: var(--surface);
  white-space: nowrap;
  transition: all 0.15s;
}
.chip:hover {
  border-color: var(--orange);
  color: var(--orange);
  background: #fff7ed;
}
</style>
