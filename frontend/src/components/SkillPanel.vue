<template>
  <div v-if="visible" class="overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>技能中心 · 共 {{ skills.length }} 个</h3>
        <button class="close" @click="$emit('close')">×</button>
      </div>

      <div class="hint">内置技能可直接在对话中触发；MCP 技能接入后即可调用外部计算服务</div>

      <div class="list">
        <div v-for="s in skills" :key="s.id" class="skill-item">
          <div class="skill-top">
            <span class="name">{{ s.name }}</span>
            <span class="src" :class="s.source">{{ s.source === 'mcp' ? 'MCP' : '内置' }}</span>
          </div>
          <div class="desc">{{ s.description }}</div>
          <div class="meta">
            <span class="cat">{{ s.category }}</span>
            <span class="status" :class="s.status">{{ s.status === 'available' ? '可用' : '预留接入' }}</span>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-primary" @click="$emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { Skill } from '@/types'

defineProps<{ visible: boolean }>()
defineEmits<{ (e: 'close'): void }>()

// mock 技能数据（联调时替换为 MCP bdf_list_skills / GET /api/skills）
const skills = ref<Skill[]>([
  { id: 's1', name: 'TADF 计算', description: '热激活延迟荧光材料的光谱计算工作流', category: '光谱', source: 'mcp', status: 'pending' },
  { id: 's2', name: '偶氮苯多组态', description: '光开关分子的多组态（CASSCF）计算', category: '多组态', source: 'mcp', status: 'pending' },
  { id: 's3', name: '光谱计算工作流', description: '吸收 / 发射光谱的 TD-DFT 全流程', category: '光谱', source: 'builtin', status: 'available' },
  { id: 's4', name: '热化学计算', description: '焓 / 熵 / 自由能等热力学量计算', category: '热化学', source: 'builtin', status: 'available' },
])
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--surface);
  border-radius: 16px;
  width: 560px;
  max-width: 92vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.modal-header h3 {
  font-size: 16px;
}
.close {
  border: none;
  background: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text-secondary);
  line-height: 1;
}

.hint {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
}

.list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skill-item {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
}

.skill-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.src {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.src.builtin {
  background: var(--amber-bg);
  color: var(--amber-text);
}
.src.mcp {
  background: var(--purple-bg);
  color: var(--purple-text);
}

.desc {
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
  margin-bottom: 8px;
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}
.cat {
  color: var(--text-secondary);
}
.status {
  padding: 1px 8px;
  border-radius: 10px;
}
.status.available {
  background: var(--green-bg);
  color: var(--green-text);
}
.status.pending {
  background: #f5f5f4;
  color: var(--text-secondary);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}
.modal-footer .btn {
  padding: 10px 20px;
}
</style>
