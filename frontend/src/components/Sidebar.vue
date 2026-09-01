<template>
  <aside class="sidebar" :class="{ collapsed }">
    <!-- 顶部：品牌 + 收起/展开 -->
    <div class="top">
      <span v-if="!collapsed" class="name">Quantum Agent</span>
      <button class="collapse" :title="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="toggle">
        <span v-if="collapsed" class="burger">☰</span>
        <span v-else>«</span>
      </button>
    </div>

    <div class="scroll">
      <ConversationList :collapsed="collapsed" />
    </div>

    <!-- 底部：知识库 / 工具 / 记忆 / 设置 / 账户 -->
    <div class="bottom">
      <button class="nav-item" title="知识库" @click="showKnowledge = true">
        <span class="icon">▤</span>
        <span v-if="!collapsed" class="label">知识库</span>
      </button>
      <button class="nav-item" title="技能" @click="showSkills = true">
        <span class="icon">✦</span>
        <span v-if="!collapsed" class="label">技能</span>
      </button>
      <button class="nav-item" title="工具清单" @click="onTools">
        <span class="icon">⚒</span>
        <span v-if="!collapsed" class="label">工具清单</span>
      </button>
      <button class="nav-item" title="记忆中心" @click="$emit('show-memory')">
        <span class="icon">◉</span>
        <span v-if="!collapsed" class="label">记忆中心</span>
      </button>
      <button class="nav-item" title="设置" @click="showSettings = true">
        <span class="icon">⚙</span>
        <span v-if="!collapsed" class="label">设置</span>
      </button>

      <div class="user" :class="{ collapsed }">
        <span class="avatar">{{ initial }}</span>
        <span v-if="!collapsed" class="username">{{ username }}</span>
        <button v-if="!collapsed" class="logout" title="退出登录" @click="$emit('logout')">退出</button>
      </div>
    </div>

    <ConfigModal :visible="showKnowledge" mode="knowledge" @close="showKnowledge = false" />
    <ConfigModal :visible="showSettings" mode="settings" @close="showSettings = false" />
    <SkillPanel :visible="showSkills" @close="showSkills = false" />
  </aside>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import ConversationList from './sidebar/ConversationList.vue'
import ConfigModal from './sidebar/ConfigModal.vue'
import SkillPanel from './SkillPanel.vue'

defineEmits<{ (e: 'show-memory'): void; (e: 'logout'): void }>()

const auth = useAuthStore()

const COLLAPSE_KEY = 'qap_sidebar_collapsed'
const collapsed = ref(localStorage.getItem(COLLAPSE_KEY) === '1')

const username = computed(() => auth.user?.username || 'guest')
const initial = computed(() => (username.value[0] || 'G').toUpperCase())

const showKnowledge = ref(false)
const showSkills = ref(false)
const showSettings = ref(false)

function toggle() {
  collapsed.value = !collapsed.value
  localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
}

function onTools() {
  alert('工具清单（mock 占位，联调后接 GET /api/tools）')
}
</script>

<style scoped>
.sidebar {
  width: 260px;
  flex-shrink: 0;
  height: 100%;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
  overflow: hidden;
}
.sidebar.collapsed {
  width: 68px;
}

.top {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.sidebar.collapsed .top {
  justify-content: center;
  padding: 14px 0;
}

.name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
}

.collapse {
  width: 34px;
  height: 34px;
  border: none;
  background: none;
  font-size: 20px;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.collapse:hover {
  background: #f5f5f4;
  color: var(--text);
}
.burger {
  font-size: 20px;
}

.scroll {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.bottom {
  border-top: 1px solid var(--border);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex-shrink: 0;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: none;
  background: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text);
  text-align: left;
  transition: background 0.12s;
  white-space: nowrap;
}
.nav-item:hover {
  background: #f5f5f4;
}
.sidebar.collapsed .nav-item {
  justify-content: center;
  padding: 10px 0;
}
.nav-item .icon {
  width: 24px;
  flex-shrink: 0;
  text-align: center;
  font-size: 18px;
  color: var(--text-secondary);
}
.nav-item .label {
  flex: 1;
}

.user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  margin-top: 6px;
}
.user.collapsed {
  border-top: none;
  margin-top: 0;
  justify-content: center;
  padding: 10px 0;
}

.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #44403c;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.username {
  flex: 1;
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logout {
  border: none;
  background: none;
  font-size: 12px;
  color: var(--orange);
  cursor: pointer;
  padding: 4px;
}
.logout:hover {
  text-decoration: underline;
}
</style>
