<template>
  <div class="settings-card">
    <h3 class="card-title">
      <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
      访问令牌
    </h3>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">状态</span>
        <span class="setting-desc">设置后访问 API 需携带令牌，防止局域网内他人访问并操作账号（默认关闭）。令牌只保存在本机浏览器。</span>
      </div>
      <div class="setting-control">
        <el-tag :type="enabled ? 'success' : 'info'">{{ enabled ? '已启用' : '未启用' }}</el-tag>
      </div>
    </div>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">新令牌</span>
        <span class="setting-desc">建议使用随机长字符串；保存后立即生效，本浏览器自动携带。清除令牌可恢复开放访问。</span>
      </div>
      <div class="setting-control">
        <el-input
          v-model="newToken"
          type="password"
          show-password
          placeholder="输入新令牌，留空则清除"
          style="width: 300px"
        />
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        <el-button v-if="enabled" @click="handleClear">清除令牌</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

defineProps<{ enabled: boolean }>()
const emit = defineEmits<{
  save: [token: string]
  clear: []
}>()

const newToken = ref('')
const saving = ref(false)

const handleSave = async () => {
  const token = newToken.value.trim()
  if (!token) {
    ElMessage.warning('请输入新令牌；如要清除请点「清除令牌」')
    return
  }
  saving.value = true
  try {
    await emit('save', token)
    newToken.value = ''
  } finally {
    saving.value = false
  }
}

const handleClear = () => {
  emit('clear')
}
</script>
