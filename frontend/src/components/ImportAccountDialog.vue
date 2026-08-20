<template>
    <el-dialog
      :model-value="modelValue"
      :show-close="!importStarted || importDone"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :width="importStarted ? '520px' : '660px'"
      align-center
      class="import-account-dialog"
      @close="handleClose"
    >
      <template #header>
        <div class="import-dialog-header">
          <div class="import-dialog-title">
            <el-icon class="title-icon"><Upload /></el-icon>
            <span>导入用户账号</span>
          </div>
          <div class="import-dialog-sub">通过 Cookie 字符串快速绑定已有平台账号</div>
        </div>
      </template>

      <!-- 输入阶段：左右分栏（左选平台 / 右输入 cookie） -->
      <template v-if="!importStarted">
        <div class="import-form-split">
          <!-- 左：平台扁平卡片列表 -->
          <div class="split-left">
            <div class="split-section-label">
              <span class="dot">●</span>
              <span>选择平台</span>
            </div>
            <el-input
              v-model="platformSearch"
              class="platform-search"
              placeholder="搜索平台..."
              :prefix-icon="Search"
              clearable
              size="small"
            />
            <div class="platform-list">
              <div
                v-for="p in filteredImportPlatforms"
                :key="p.id"
                :class="['platform-card-flat', { 'is-selected': importForm.platformId === p.id }]"
                @click="importForm.platformId = p.id"
              >
                <div class="card-logo-wrap" :style="{ background: getPlatformBg(p.name) }">
                  <img
                    v-if="getPlatformLogo(p.name)"
                    :src="getPlatformLogo(p.name) || undefined"
                    :alt="p.name"
                    class="card-logo"
                  />
                  <span v-else class="card-letter" :style="{ color: getPlatformColor(p.name) }">
                    {{ p.letter }}
                  </span>
                </div>
                <div class="card-text">
                  <div class="card-name">{{ p.name }}</div>
                </div>
                <el-icon v-if="importForm.platformId === p.id" class="card-check">
                  <Select />
                </el-icon>
              </div>
              <div v-if="!filteredImportPlatforms.length" class="empty-platform">
                {{ importSupportedPlatforms.length ? '未匹配到平台' : '暂无支持导入的平台' }}
              </div>
            </div>
          </div>

          <!-- 右：cookie 输入 -->
          <div class="split-right">
            <div class="split-section-label">
              <span class="dot">●</span>
              <span>Cookie 字符串</span>
            </div>
            <el-input
              v-model="importForm.cookieStr"
              type="textarea"
              resize="none"
              class="import-textarea"
              placeholder="k1=v1; k2=v2; k3=v3 ..."
            />
            <div class="cookie-tip">
              <el-icon><InfoFilled /></el-icon>
              <span>从浏览器 DevTools → Network → 任意请求 → Request Headers → Cookie 复制整段</span>
            </div>
          </div>
        </div>
      </template>

      <!-- 进度阶段：自绘 4 步进度条 -->
      <template v-else>
        <div class="import-progress">
          <div class="import-progress-header">
            <div class="platform-pill" v-if="currentImportPlatform">
              <span class="platform-letter" :style="{ background: getPlatformColor(currentImportPlatform.name) }">
                {{ currentImportPlatform.letter }}
              </span>
              <span class="platform-name">{{ currentImportPlatform.name }}</span>
            </div>
          </div>

          <!-- 顶部进度条 (n/4) -->
          <div class="progress-bar-wrap">
            <div class="progress-bar">
              <div
                class="progress-bar-fill"
                :class="{ 'is-error': importFailed }"
                :style="{ width: progressPercent + '%' }"
              ></div>
            </div>
            <div class="progress-bar-text">
              {{ importFailed ? '已中断' : `${importActiveStep}/${importSteps.length}` }}
            </div>
          </div>

          <!-- 步骤列表 -->
          <ul class="step-list">
            <li
              v-for="(s, idx) in importSteps"
              :key="idx"
              :class="['step-item', `is-${s.status}`]"
            >
              <div class="step-indicator">
                <el-icon v-if="s.status === 'finish'" class="step-icon finish"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="s.status === 'error'" class="step-icon error"><CircleCloseFilled /></el-icon>
                <el-icon v-else-if="s.status === 'process'" class="step-icon process is-loading"><Loading /></el-icon>
                <span v-else class="step-num">{{ idx + 1 }}</span>
              </div>
              <div class="step-content">
                <div class="step-title">{{ s.title }}</div>
                <div class="step-description" :class="{ 'is-error': s.status === 'error' }">
                  {{ s.description || '等待中...' }}
                </div>
              </div>
            </li>
          </ul>

          <!-- 完成态：账号预览卡片 -->
          <transition name="fade-up">
            <div v-if="importDone && importResult" class="result-card">
              <img
                v-if="importResult.avatar"
                :src="importResult.avatar"
                class="result-avatar"
                @error="importResult.avatar = ''"
              />
              <div v-else class="result-avatar-fallback">
                {{ (importResult.userName || '?').charAt(0) }}
              </div>
              <div class="result-info">
                <div class="result-name">{{ importResult.userName || '未识别昵称' }}</div>
                <div class="result-meta">已成功导入为账号 #{{ importResult.accountId }}</div>
              </div>
            </div>
          </transition>
        </div>
      </template>

      <template #footer>
        <template v-if="!importStarted">
          <el-button @click="handleClose" class="footer-btn">取消</el-button>
          <el-button
            type="primary"
            :loading="importStarting"
            :disabled="!importForm.platformId || !importForm.cookieStr.trim()"
            class="footer-btn-primary"
            @click="submitImport"
          >
            <el-icon v-if="!importStarting"><Position /></el-icon>
            <span>开始导入</span>
          </el-button>
        </template>
        <template v-else>
          <el-button
            :disabled="!importDone"
            :type="importFailed ? 'danger' : 'primary'"
            class="footer-btn-primary"
            @click="handleClose"
          >
            {{ importFailed ? '关闭' : (importDone ? '完成' : '处理中...') }}
          </el-button>
        </template>
      </template>
    </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Search, Select, Position, InfoFilled, CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { accountApi } from '@/api/account'
import { getErrorMessage } from '@/utils/error'
import { type ApiResponse } from '@/utils/request'
import { getPlatformColor, getPlatformBg, getPlatformLogo } from '@/components/accountCardShared'

/** cookie 导入支持的平台 */
interface ImportPlatform {
  id: number
  key?: string
  name: string
  letter?: string
}

/** 导入 4 步进度条目 */
interface ImportStep {
  title: string
  description: string
  status: 'wait' | 'process' | 'finish' | 'error'
}

/** 导入完成态展示数据 */
interface ImportResult {
  accountId?: number | string
  userName?: string
  avatar?: string
}

/** SSE 导入进度 payload */
interface ImportStreamPayload {
  step?: number | string
  status?: string
  msg?: string
  account_id?: number | string
  userName?: string
  avatar?: string
}

/** cookie 导入表单 */
interface ImportForm {
  platformId: number | null
  cookieStr: string
}

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success'): void
}>()

// 打开时重置并拉取支持导入的平台列表
watch(() => props.modelValue, (open) => {
  if (!open) return
  resetImportDialog()
  ;(async () => {
    try {
      const res = (await accountApi.getImportSupportedPlatforms()) as ApiResponse<ImportPlatform[]>
      if (res.code === 200 && res.data) {
        importSupportedPlatforms.value = res.data
      }
    } catch (e) {
      ElMessage.error('获取支持导入的平台列表失败')
    }
  })()
})

onBeforeUnmount(() => {
  if (importEventSource) {
    importEventSource.close()
    importEventSource = null
  }
})

const importSupportedPlatforms = ref<ImportPlatform[]>([])  // [{id, key, name, letter}, ...]
const platformSearch = ref('')
const filteredImportPlatforms = computed<ImportPlatform[]>(() => {
  const kw = platformSearch.value.trim().toLowerCase()
  if (!kw) return importSupportedPlatforms.value
  return importSupportedPlatforms.value.filter(p =>
    p.name.toLowerCase().includes(kw) ||
    (p.key || '').toLowerCase().includes(kw)
  )
})
const importForm = reactive<ImportForm>({
  platformId: null,
  cookieStr: '',
})
const importStarted = ref(false)
const importStarting = ref(false)
const importActiveStep = ref(0)   // 当前进行到的 step (0-based)
const importDone = ref(false)      // 全部完成 / 失败时为 true，允许关闭
const importFailed = ref(false)    // 失败态：进度条标红，关闭按钮变 danger
const importResult = ref<ImportResult | null>(null)     // { accountId, userName, avatar } 完成态展示
// EventSource 是非响应式对象，用普通 let 持有；放在 ref 里会被 Vue proxy 包一层
// 导致 close() 等行为不可靠。仿 LoginDialog.vue 的 eventSources Map 写法。
let importEventSource: EventSource | null = null

// 顶部进度条百分比 (0/25/50/75/100)
const progressPercent = computed(() => {
  if (importFailed.value) return 100
  const done = importSteps.value.filter(s => s.status === 'finish').length
  return Math.round((done / importSteps.value.length) * 100)
})

// 当前正在导入的平台（用于头部 pill 展示）
const currentImportPlatform = computed<ImportPlatform | null>(() => {
  if (!importForm.platformId) return null
  return importSupportedPlatforms.value.find(p => p.id === importForm.platformId) || null
})

// 4 步进度，每项 { title, description, status: 'wait'|'process'|'finish'|'error' }
const importSteps = ref<ImportStep[]>([
  { title: '解析 cookie 字符串', description: '等待中...', status: 'wait' },
  { title: '生成 cookie 文件',   description: '等待中...', status: 'wait' },
  { title: '同步用户资料',        description: '等待中...', status: 'wait' },
  { title: '导入完成',            description: '等待中...', status: 'wait' },
])

const resetImportDialog = () => {
  importStarted.value = false
  importStarting.value = false
  importActiveStep.value = 0
  importDone.value = false
  importFailed.value = false
  importResult.value = null
  importForm.platformId = null
  importForm.cookieStr = ''
  platformSearch.value = ''
  importSteps.value = [
    { title: '解析 cookie 字符串', description: '等待中...', status: 'wait' },
    { title: '生成 cookie 文件',   description: '等待中...', status: 'wait' },
    { title: '同步用户资料',        description: '等待中...', status: 'wait' },
    { title: '导入完成',            description: '等待中...', status: 'wait' },
  ]
  if (importEventSource) {
    importEventSource.close()
    importEventSource = null
  }
}

const handleClose = () => {
  if (importEventSource) {
    importEventSource.close()
    importEventSource = null
  }
  emit('update:modelValue', false)
  // 给 el-dialog 关闭动画留 200ms 再清状态
  setTimeout(() => resetImportDialog(), 200)
}

const submitImport = async () => {
  if (!importForm.platformId || !importForm.cookieStr.trim()) {
    ElMessage.warning('请选择平台并粘贴 cookie 字符串')
    return
  }
  importStarting.value = true
  importStarted.value = true

  // 1. 启动任务
  let taskId: number | string
  try {
    const res = (await accountApi.startImportAccount({
      type: importForm.platformId,
      cookie_str: importForm.cookieStr.trim(),
    })) as ApiResponse<{ task_id: number | string }>
    if (res.code !== 200 || !res.data || !res.data.task_id) {
      throw new Error(res.msg || '启动导入任务失败')
    }
    taskId = res.data.task_id
  } catch (e) {
    importStarting.value = false
    importSteps.value[0].status = 'error'
    importSteps.value[0].description = getErrorMessage(e)
    importDone.value = true
    importFailed.value = true
    return
  }
  importStarting.value = false

  // 2. SSE 监听进度
  const es = new EventSource(`/importAccount/stream?task_id=${taskId}`)
  importEventSource = es

  es.onmessage = (event) => {
    let payload: ImportStreamPayload
    try {
      payload = JSON.parse(event.data)
    } catch (_) {
      return
    }
    const step = Number(payload.step || 0)  // 1..4，error 时可能为 0

    if (payload.status === 'error') {
      // 标红当前 step（如果 step 缺失或越界，标红最后一个）
      const idx = step >= 1 && step <= 4 ? step - 1 : Math.max(0, importActiveStep.value)
      importSteps.value[idx].status = 'error'
      importSteps.value[idx].description = payload.msg || '未知错误'
      importDone.value = true
      importFailed.value = true
      es.close()
      importEventSource = null
      ElMessage.error(`导入失败: ${payload.msg || ''}`)
      return
    }

    if (payload.status === 'done') {
      importActiveStep.value = 4
      for (let i = 0; i < 4; i++) {
        importSteps.value[i].status = 'finish'
        importSteps.value[i].description = importSteps.value[i].description || '完成'
      }
      importSteps.value[3].description = '已完成'
      importResult.value = {
        accountId: payload.account_id,
        userName: payload.userName,
        avatar: payload.avatar,
      }
      importDone.value = true
      importFailed.value = false
      es.close()
      importEventSource = null
      ElMessage.success('导入成功')
      // 刷新账号列表
      emit('success')
      return
    }

    if (payload.status === 'running' && step >= 1 && step <= 4) {
      const idx = step - 1
      importActiveStep.value = idx
      importSteps.value[idx].status = 'process'
      importSteps.value[idx].description = payload.msg || '处理中...'
      // 已完成的前置步骤保持 finish
      for (let i = 0; i < idx; i++) {
        if (importSteps.value[i].status === 'process') {
          importSteps.value[i].status = 'finish'
        }
      }
    }
  }

  es.onerror = () => {
    // EventSource 出错时通常意味着后端已断开连接（task 已结束）。
    // 如果 importDone 还没置 true，说明后端异常断开，标红最后活跃 step。
    if (!importDone.value) {
      const idx = importActiveStep.value
      importSteps.value[idx].status = 'error'
      importSteps.value[idx].description = '连接中断，请稍后重试'
      importDone.value = true
      ElMessage.error('导入连接中断')
    }
    es.close()
    importEventSource = null
  }
}
</script>
