<template>
  <div class="auth-overlay">
    <div class="auth-card">
      <h2>{{ isRegister ? '注册' : '登录' }}</h2>
      <p class="sub">{{ isRegister ? '创建账号以使用平台' : '登录后使用 Quantum Agent Platform' }}</p>

      <div v-if="error" class="error">{{ error }}</div>

      <form @submit.prevent="handleSubmit">
        <input v-model="username" type="text" placeholder="用户名" autocomplete="username" />
        <input v-if="isRegister" v-model="email" type="email" placeholder="邮箱" autocomplete="email" />
        <input v-model="password" type="password" placeholder="密码" autocomplete="current-password" />
        <button type="submit" :disabled="loading">
          <span v-if="loading" class="spinner"></span>{{ loading ? (isRegister ? '注册中...' : '登录中...') : (isRegister ? '注册' : '登录') }}
        </button>
      </form>

      <div class="divider"><span>或</span></div>

      <button type="button" class="guest" :disabled="guestLoading" @click="handleGuest">
        {{ guestLoading ? '进入中...' : '直接进入（游客模式）' }}
      </button>

      <div class="switch">
        <span>{{ isRegister ? '已有账号？' : '还没有账号？' }}</span>
        <a @click="toggleMode">{{ isRegister ? '去登录' : '立即注册' }}</a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const isRegister = ref(false)
const username = ref('')
const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const guestLoading = ref(false)

function toggleMode() {
  isRegister.value = !isRegister.value
  error.value = ''
}

async function handleGuest() {
  error.value = ''
  guestLoading.value = true
  try {
    await auth.guest()
    router.push({ name: 'chat' })
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    guestLoading.value = false
  }
}

async function handleSubmit() {
  error.value = ''

  if (!username.value.trim() || !password.value) {
    error.value = '请填写用户名和密码'
    return
  }
  if (isRegister.value && !email.value.trim()) {
    error.value = '请填写邮箱'
    return
  }

  loading.value = true
  try {
    if (isRegister.value) {
      await auth.register(username.value.trim(), email.value.trim(), password.value)
    } else {
      await auth.login(username.value.trim(), password.value)
    }
    router.push({ name: 'chat' })
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.auth-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 40px 36px;
  width: 380px;
  max-width: 90vw;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
}

h2 {
  font-size: 22px;
  margin-bottom: 6px;
}

.sub {
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 24px;
}

.error {
  color: #ef4444;
  font-size: 12px;
  margin-bottom: 10px;
  background: var(--red-bg);
  border: 1px solid var(--red-border);
  border-radius: 8px;
  padding: 8px 12px;
}

input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 14px;
  margin-bottom: 12px;
  outline: none;
  background: #fafaf9;
  transition: border-color 0.15s;
}
input:focus {
  border-color: var(--orange);
}

button {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 10px;
  background: var(--orange);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 4px;
}
button:hover:not(:disabled) {
  background: var(--orange-hover);
}
button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.divider {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0 12px;
  color: var(--text-secondary);
  font-size: 12px;
}
.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

button.guest {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text);
  font-weight: 500;
  margin-top: 0;
}
button.guest:hover:not(:disabled) {
  background: #fafaf9;
  color: var(--text);
}

.switch {
  text-align: center;
  margin-top: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}
.switch a {
  color: var(--orange);
  cursor: pointer;
  font-weight: 600;
  margin-left: 4px;
}
</style>
