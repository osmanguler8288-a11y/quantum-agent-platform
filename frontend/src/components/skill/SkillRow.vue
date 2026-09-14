<template>
  <div class="skill-row" :class="{ off: !skill.enabled }" @click="$emit('detail', skill)">
    <div class="skill-icon">✦</div>

    <div class="skill-main">
      <div class="title-line">
        <span class="skill-name">{{ skill.name }}</span>
        <span class="badge steps">{{ skill.steps.length }} 步</span>
        <span v-if="!skill.enabled" class="badge off">已停用</span>
      </div>
      <div class="skill-desc">{{ skill.description || '（未填写描述）' }}</div>

      <!-- 工具链：小节点 + 箭头，超宽截断（完整链条看详情） -->
      <div v-if="skill.steps.length" class="chain">
        <template v-for="(s, i) in skill.steps" :key="i">
          <span v-if="i > 0" class="arrow">→</span>
          <span class="node">{{ stepToolName(s, toolMap) }}</span>
        </template>
      </div>
    </div>

    <div class="skill-side">
      <span class="time">{{ skill.run_count ? formatRelativeTime(skill.last_run_at) : '—' }}</span>
      <span class="cnt">运行 {{ skill.run_count }} 次</span>
    </div>

    <div class="switch" @click.stop>
      <div
        class="switch-track"
        :class="{ on: skill.enabled }"
        role="switch"
        :aria-checked="skill.enabled"
        :title="skill.enabled ? '停用该技能' : '启用该技能'"
        @click="$emit('toggle', skill)"
      />
    </div>

    <div class="card-actions" @click.stop>
      <button class="icon-btn" title="查看详情" @click="$emit('detail', skill)">👁</button>
      <button class="icon-btn" title="编辑" @click="$emit('edit', skill)">✎</button>
      <button class="icon-btn danger" title="删除" @click="$emit('remove', skill)">🗑</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatRelativeTime } from '@/api/conversation'
import { stepToolName, type Skill } from '@/api/skill'
import type { Tool } from '@/api/tools'

defineProps<{
  skill: Skill
  /** 工具表：步骤未回填 tool_name 时兜底展示工具名 */
  toolMap: Map<number, Tool>
}>()

defineEmits<{
  (e: 'detail', skill: Skill): void
  (e: 'edit', skill: Skill): void
  (e: 'remove', skill: Skill): void
  (e: 'toggle', skill: Skill): void
}>()
</script>

<style scoped>
.skill-row {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  gap: 14px;
  transition: box-shadow 0.15s, border-color 0.15s;
  cursor: pointer;
}
.skill-row:hover {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.07);
  border-color: var(--orange-border);
}
.skill-row.off .skill-icon { opacity: 0.55; }
.skill-row.off .skill-main { opacity: 0.65; }

.skill-icon {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  flex-shrink: 0;
  background: var(--orange-light);
  color: var(--orange);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
}

.skill-main {
  flex: 1;
  min-width: 0;
}
.title-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.skill-name {
  font-size: 13.5px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 420px;
}
.badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
  flex-shrink: 0;
}
.badge.steps {
  background: var(--orange-light);
  color: var(--orange-hover);
}
.badge.off {
  background: #f5f5f4;
  color: var(--text-secondary);
}

.skill-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 640px;
}

.chain {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-secondary);
  overflow: hidden;
  white-space: nowrap;
}
.chain .node {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1px 8px;
  flex-shrink: 0;
}
.chain .arrow {
  color: #a8a29e;
  flex-shrink: 0;
}

.skill-side {
  flex-shrink: 0;
  width: 120px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-end;
}
.skill-side .time {
  font-size: 12.5px;
  font-weight: 600;
}
.skill-side .cnt {
  font-size: 11.5px;
  color: var(--text-secondary);
}

.switch {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}
.switch-track {
  width: 34px;
  height: 20px;
  border-radius: 10px;
  background: #d6d3d1;
  position: relative;
  cursor: pointer;
  transition: background 0.15s;
}
.switch-track.on { background: var(--orange); }
.switch-track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: left 0.15s;
}
.switch-track.on::after { left: 16px; }

.card-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
}
.icon-btn:hover {
  background: #f5f5f4;
  color: var(--text);
}
.icon-btn.danger:hover {
  background: var(--red-bg);
  color: var(--red-text);
}
</style>
