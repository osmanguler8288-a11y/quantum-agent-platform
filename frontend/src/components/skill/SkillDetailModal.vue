<template>
  <div v-if="visible" class="overlay" @click.self="close">
    <div class="modal">
      <template v-if="detail">
        <div class="modal-head">
          <div class="head-row">
            <div class="head-icon">✦</div>
            <div class="head-main">
              <div class="head-title">
                {{ detail.name }}
                <span class="badge steps">{{ detail.steps.length }} 步</span>
                <span class="badge" :class="detail.enabled ? 'on' : 'off'">
                  {{ detail.enabled ? '已启用' : '已停用' }}
                </span>
              </div>
              <div class="meta-strip">
                <span>更新于 <b>{{ formatTime(detail.updated_at) }}</b></span><span class="sep">·</span>
                <span>运行 <b>{{ detail.run_count }}</b> 次</span><span class="sep">·</span>
                <span>成功率 <b>{{ formatSkillRate(detail.success_rate) }}</b></span><span class="sep">·</span>
                <span>平均耗时 <b>{{ formatSkillDuration(detail.avg_duration_sec) }}</b></span>
              </div>
            </div>
            <button class="close" @click="close">✕</button>
          </div>
        </div>

        <div class="modal-body">
          <div class="section-title">描述</div>
          <div class="desc-block">
            {{ detail.description || '（未填写描述）' }}
          </div>

          <div class="flow">
            <div class="section-title">工作流（{{ detail.steps.length }} 步）</div>
            <div class="flow-list">
              <div v-for="(s, i) in detail.steps" :key="i" class="flow-step">
                <div class="flow-no">{{ i + 1 }}</div>
                <div class="flow-main">
                  <div class="flow-tool">
                    <span class="tool-name">{{ stepToolName(s, toolMap) }}</span>
                    <span v-if="kindLabel(s)" class="badge kind">{{ kindLabel(s) }}</span>
                  </div>
                  <div v-if="s.note" class="flow-note">{{ s.note }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="stats-row">
            <div class="stat">
              <div class="num">{{ detail.run_count }}</div>
              <div class="lbl">总运行次数</div>
            </div>
            <div class="stat">
              <div class="num">{{ formatSkillRate(detail.success_rate) }}</div>
              <div class="lbl">成功率</div>
            </div>
            <div class="stat">
              <div class="num">{{ formatSkillDuration(detail.avg_duration_sec) }}</div>
              <div class="lbl">平均耗时</div>
            </div>
            <div class="stat">
              <div class="num">{{ formatRelativeTime(detail.last_run_at) }}</div>
              <div class="lbl">最近运行</div>
            </div>
          </div>

          <div class="use-tip">
            💡 在对话中说「用 <b>{{ detail.name }}</b> 处理这批分子」即可调用该子代理。
          </div>
        </div>

        <div class="modal-foot">
          <button class="btn btn-ghost" @click="close">关闭</button>
          <button class="btn btn-primary-lg" @click="$emit('try', detail)">在对话中试用</button>
        </div>
      </template>

      <div v-else-if="loadError" class="state-block">
        <p>{{ loadError }}</p>
        <button class="btn btn-ghost" @click="load">重试</button>
      </div>
      <div v-else class="state-block">加载中…</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatRelativeTime } from '@/api/conversation'
import {
  fetchSkill, formatSkillDuration, formatSkillRate, stepToolName, stepSourceLabel,
  type Skill,
} from '@/api/skill'
import { formatTime, type Tool } from '@/api/tools'

const props = defineProps<{
  visible: boolean
  skillId: number | null
  /** 工具表：步骤未回填 tool_name 时兜底展示工具名 */
  toolMap: Map<number, Tool>
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'try', skill: Skill): void
}>()

const detail = ref<Skill | null>(null)
const loadError = ref('')

watch(
  () => [props.visible, props.skillId] as const,
  ([visible]) => {
    if (visible) load()
  },
  { immediate: true },
)

async function load() {
  if (props.skillId === null) return
  detail.value = null
  loadError.value = ''
  try {
    detail.value = await fetchSkill(props.skillId)
  } catch (e) {
    loadError.value = `技能详情加载失败：${(e as Error).message}`
  }
}

function kindLabel(s: Skill['steps'][number]): string {
  return stepSourceLabel(s)
}

function close() {
  emit('close')
}
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(28, 25, 23, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
}
.modal {
  background: var(--surface);
  border-radius: 16px;
  width: 640px;
  max-width: 100%;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow: hidden;
}

.modal-head {
  padding: 20px 24px 0;
  flex-shrink: 0;
}
.head-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.head-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  flex-shrink: 0;
  background: var(--orange-light);
  color: var(--orange);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}
.head-main {
  flex: 1;
  min-width: 0;
}
.head-title {
  font-size: 16px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
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
.badge.on {
  background: var(--green-bg);
  color: var(--green-text);
}
.badge.off {
  background: #f5f5f4;
  color: var(--text-secondary);
}
.badge.kind {
  background: var(--purple-bg);
  color: var(--purple-text);
}
.close {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: none;
  background: none;
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
  flex-shrink: 0;
}
.close:hover {
  background: #f5f5f4;
  color: var(--text);
}

.meta-strip {
  margin-top: 10px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-wrap: nowrap;
  justify-content: flex-start;
  gap: 5px;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.meta-strip b {
  color: var(--text);
  font-weight: 600;
}
.meta-strip .sep { color: #d6d3d1; }

.modal-body {
  padding: 16px 24px 4px;
  overflow-y: auto;
}

.section-title {
  font-size: 12.5px;
  font-weight: 700;
  margin-bottom: 8px;
}
.desc-block {
  background: var(--bg);
  border-radius: 10px;
  padding: 11px 13px;
  font-size: 12.5px;
  color: var(--text);
  line-height: 1.7;
}

.flow { margin-top: 18px; }
.flow-list {
  position: relative;
  padding-left: 2px;
}
.flow-step {
  display: flex;
  gap: 12px;
  position: relative;
  padding-bottom: 14px;
}
.flow-step:last-child { padding-bottom: 0; }
.flow-step::before {
  content: '';
  position: absolute;
  left: 12px;
  top: 26px;
  bottom: -2px;
  width: 2px;
  background: var(--border);
}
.flow-step:last-child::before { display: none; }
.flow-no {
  width: 25px;
  height: 25px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--orange-light);
  color: var(--orange-hover);
  font-size: 11.5px;
  font-weight: 700;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid var(--surface);
}
.flow-main {
  flex: 1;
  min-width: 0;
  padding-top: 2px;
}
.flow-tool {
  display: flex;
  align-items: center;
  gap: 8px;
}
.flow-tool .tool-name {
  font-size: 13px;
  font-weight: 700;
}
.flow-note {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 3px;
  line-height: 1.6;
}

.stats-row {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.stat {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  text-align: left;
}
.stat .num {
  font-size: 16px;
  font-weight: 700;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.stat .lbl {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.use-tip {
  margin-top: 14px;
  padding: 10px 12px;
  background: var(--orange-light);
  border-radius: 10px;
  font-size: 12px;
  color: var(--orange-hover);
  line-height: 1.6;
}
.use-tip b { font-weight: 700; }

.state-block {
  padding: 60px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 24px 20px;
  flex-shrink: 0;
}
.btn {
  border: none;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 600;
  font-family: inherit;
  transition: background 0.15s;
}
.btn-ghost {
  background: #f5f5f4;
  color: var(--text);
  padding: 10px 20px;
  font-size: 13px;
}
.btn-ghost:hover { background: #e7e5e4; }
.btn-primary-lg {
  background: var(--orange);
  color: #fff;
  padding: 10px 22px;
  font-size: 13px;
}
.btn-primary-lg:hover { background: var(--orange-hover); }
</style>
