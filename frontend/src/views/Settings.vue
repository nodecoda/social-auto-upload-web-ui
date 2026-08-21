<template>
  <div class="settings-page" v-loading="loading">
    <h1 class="page-title">系统设置</h1>
    <p class="page-subtitle">配置应用偏好</p>

    <!-- 代理设置 -->
    <ProxySettingsCard v-model:proxy-url="settings.proxyUrl" :overseas-platforms="overseasPlatforms" />

    <!-- 发布设置 -->
    <PublishSettingsCard
      v-model:auto-fill-title="settings.autoFillTitle"
      v-model:auto-save-draft="settings.autoSaveDraft"
      v-model:auto-save-interval="settings.autoSaveInterval"
      v-model:account-check-mode="settings.accountCheckMode"
    />

    <!-- 渠道黑名单 -->
    <BlacklistCard :platforms="disabledPlatformObjects" @open="openBlacklistDialog" @remove="removeFromBlacklist" />

    <!-- 访问令牌 -->
    <AccessTokenCard :enabled="settings.accessTokenSet" @save="saveToken" @clear="clearToken" />

    <!-- 文件存储 -->
    <StorageSettingsCard :storage="settings.storage" />
    <!-- 缓存管理 -->
    <CacheSettingsCard :cache-info="cacheInfo" :clearing="clearingCache" @clear="handleClearCache" />
    <!-- 关于系统 -->
    <div class="settings-card">
      <h3 class="card-title">
        <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        技术栈
      </h3>
      <div class="tech-grid">
        <div class="tech-section">
          <h4 class="tech-section-title">版本</h4>
          <div class="version-badge">v{{ appVersion }}</div>
        </div>
        <div class="tech-section">
          <h4 class="tech-section-title">前端</h4>
          <div class="tech-item" v-for="item in frontendStack" :key="item.name">
            <span class="tech-name">{{ item.name }}</span>
            <span class="tech-version">{{ item.version }}</span>
          </div>
        </div>
        <div class="tech-section">
          <h4 class="tech-section-title">后端</h4>
          <div class="tech-item" v-for="item in backendStack" :key="item.name">
            <span class="tech-name">{{ item.name }}</span>
            <span class="tech-version">{{ item.version }}</span>
          </div>
        </div>
        <div class="tech-section">
          <h4 class="tech-section-title">浏览器引擎</h4>
          <div class="tech-item" v-for="item in browserStack" :key="item.name">
            <span class="tech-name">{{ item.name }}</span>
            <span class="tech-version">{{ item.version }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 反馈系统 -->
    <div class="settings-card">
      <h3 class="card-title">
        <el-icon class="title-icon"><ChatDotRound /></el-icon>
        反馈系统
      </h3>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">反馈邮箱</span>
          <span class="setting-desc">用于在「一键反馈」菜单提交反馈和投票。不填将无法使用这些功能</span>
        </div>
        <div class="setting-control">
          <el-input
            v-model="settings.feedbackEmail"
            placeholder="your@email.com"
            style="width: 300px"
            clearable
          />
        </div>
      </div>
    </div>

    <!-- Save button -->
    <div class="save-bar">
      <button class="save-btn" :disabled="saving" @click="handleSave">
        {{ saving ? '保存中...' : '保存设置' }}
      </button>
    </div>

    <!-- 渠道黑名单添加弹窗 -->
    <PlatformBlacklistDialog
      v-model="blacklistDialogVisible"
      :disabled-keys="appStore.disabledPlatforms"
      @confirm="onBlacklistConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ChatDotRound } from '@element-plus/icons-vue'
import { settingsApi } from '@/api/v2'
import { platformList, getPlatformByKey } from '@/config/platforms'
import { http, type ApiResponse } from '@/utils/request'
import { useAppStore } from '@/stores/app'
import PlatformBlacklistDialog from '@/components/PlatformBlacklistDialog.vue'
import ProxySettingsCard from '@/components/ProxySettingsCard.vue'
import PublishSettingsCard from '@/components/PublishSettingsCard.vue'
import BlacklistCard from '@/components/BlacklistCard.vue'
import AccessTokenCard from '@/components/AccessTokenCard.vue'
import StorageSettingsCard, { type StorageConfig, type S3Config } from '@/components/StorageSettingsCard.vue'
import CacheSettingsCard, { type CacheInfoState, type ClearCacheTarget, type CacheEntry, type LogsCacheEntry } from '@/components/CacheSettingsCard.vue'

// ===== 类型定义 =====

// 平台配置对象(来自 @/config/platforms 的 platformList 元素)
type PlatformObject = NonNullable<ReturnType<typeof getPlatformByKey>>

// 设置表单状态
interface SettingsState {
  proxyUrl: string
  autoFillTitle: boolean
  autoSaveDraft: boolean
  autoSaveInterval: number
  accountCheckMode: string
  storage: StorageConfig
  feedbackEmail: string
  accessTokenSet: boolean
}

// 后端 /api/v2/settings 返回的数据(字段可能缺省,均为可选)
interface SettingsData {
  proxyUrl?: string
  autoFillTitle?: boolean
  autoSaveDraft?: boolean
  autoSaveInterval?: number
  accountCheckMode?: string
  storage?: StorageConfig
  feedbackEmail?: string
  disabledPlatforms?: string | string[] | null
  accessTokenSet?: boolean
}

// /api/system-info 返回的缓存数据(字段可能缺省)
interface SystemInfoCache {
  frames?: CacheEntry
  logs?: LogsCacheEntry
  s3_videos?: CacheEntry
  covers?: CacheEntry
}

// /api/system-info 返回的数据
interface SystemInfoData {
  version?: string
  cache?: SystemInfoCache
}

// 清理缓存接口返回的单个目标清理结果
interface ClearCacheResult {
  cleared: number
}

// 技术栈展示项
interface TechStackItem {
  name: string
  version: string
}

const appStore = useAppStore()

// 已拉黑渠道的平台对象数组(filter(Boolean) 容错,防止后端返回不存在的 key)
// 注意: store 中存的是小写 platform key (如 'xiaohongshu'),
// 不能用 PLATFORMS[<uppercase>] 直接查,要用 getPlatformByKey
const disabledPlatformObjects = computed<PlatformObject[]>(() =>
  (appStore.disabledPlatforms as string[])
    .map((k: string) => getPlatformByKey(k))
    .filter((p): p is PlatformObject => p !== null)
)

const blacklistDialogVisible = ref(false)
const openBlacklistDialog = () => { blacklistDialogVisible.value = true }

const removeFromBlacklist = async (key: string) => {
  try {
    await appStore.removeDisabledPlatform(key)
    ElMessage.success('已从黑名单移除')
  } catch (e: unknown) {
    console.error('移除黑名单失败:', e)
    ElMessage.error('移除失败,请重试')
  }
}

const onBlacklistConfirm = async (newKeys: string[]) => {
  try {
    await appStore.addDisabledPlatforms(newKeys)
    ElMessage.success(`已添加 ${newKeys.length} 个渠道到黑名单`)
  } catch (e: unknown) {
    console.error('添加黑名单失败:', e)
    ElMessage.error('添加失败,请重试')
  }
}

const loading = ref(false)
const saving = ref(false)
const clearingCache = ref(false)
const appVersion = ref('--')
const cacheInfo = reactive<CacheInfoState>({
  frames: { count: 0, size: 0 },
  logs: { count: 0, size: 0, oldCount: 0 },
  s3_videos: { count: 0, size: 0 },
  covers: { count: 0, size: 0 },
})

const fetchSystemInfo = async () => {
  try {
    const res = (await http.get('/api/system-info')) as ApiResponse<SystemInfoData>
    if (res.code === 200 && res.data) {
      appVersion.value = res.data.version || '--'
      if (res.data.cache) {
        cacheInfo.frames = res.data.cache.frames || { count: 0, size: 0 }
        cacheInfo.logs = res.data.cache.logs || { count: 0, size: 0, oldCount: 0 }
        cacheInfo.s3_videos = res.data.cache.s3_videos || { count: 0, size: 0 }
        cacheInfo.covers = res.data.cache.covers || { count: 0, size: 0 }
      }
    }
  } catch {}
}

const handleClearCache = async (target: ClearCacheTarget) => {
  const messages: Record<ClearCacheTarget, string> = { frames: '抽帧缓存', logs: '日志文件', s3_videos: 'S3 视频缓存', covers: '封面缓存' }
  const confirmMessages: Record<ClearCacheTarget, string> = {
    frames: '确定要清理所有抽帧缓存数据吗？清理后下次使用封面功能时会重新提取视频帧。',
    logs: '确定要清理所有过期日志文件吗？',
    s3_videos: '确定要清理所有 S3 视频缓存吗？清理后下次抽帧时会重新从 S3 下载。',
    covers: '确定要清理所有封面缓存吗？清理后已设置的封面引用可能失效，需重新裁剪。',
  }
  try {
    await ElMessageBox.confirm(
      confirmMessages[target],
      '确认清理',
      { confirmButtonText: '确定清理', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  clearingCache.value = true
  try {
    const res = (await http.post('/api/clear-cache', { targets: [target] })) as ApiResponse<Partial<Record<ClearCacheTarget, ClearCacheResult>>>
    if (res.code === 200) {
      const info = res.data?.[target]
      ElMessage.success(info ? `已清理 ${info.cleared} 个${messages[target]}` : `${messages[target]}已清理`)
      fetchSystemInfo()
    } else {
      ElMessage.error(res.msg || '清理失败')
    }
  } catch {
    ElMessage.error('清理失败')
  } finally {
    clearingCache.value = false
  }
}

const settings = reactive<SettingsState>({
  proxyUrl: '',
  autoFillTitle: true,
  autoSaveDraft: true,
  autoSaveInterval: 10,
  accountCheckMode: 'pre-publish',
  storage: {
    type: 'local',
    s3: { endpoint: '', access_key: '', secret_key: '', bucket: '', region: '' },
  },
  feedbackEmail: '',
  accessTokenSet: false,
})

// 海外平台列表
const overseasPlatforms: PlatformObject[] = platformList.filter(p => ['youtube', 'tiktok'].includes(p.key))

// 技术栈版本
const frontendStack: TechStackItem[] = [
  { name: 'Vue', version: '3.5.x' },
  { name: 'Element Plus', version: '2.9.x' },
  { name: 'Vite', version: '6.3.x' },
  { name: 'Pinia', version: '3.0.x' },
  { name: 'Axios', version: '1.9.x' },
]

const backendStack: TechStackItem[] = [
  { name: 'Python', version: '3.14' },
  { name: 'Flask', version: '3.1.x' },
  { name: 'SQLite', version: '3.x' },
]

const browserStack: TechStackItem[] = [
  { name: 'CloakBrowser', version: 'latest' },
  { name: 'Chromium', version: 'latest' },
]

const fetchSettings = async () => {
  loading.value = true
  try {
    const res = (await settingsApi.getSettings()) as ApiResponse<SettingsData>
    if (res.code === 200 && res.data) {
      if (res.data.proxyUrl !== undefined) settings.proxyUrl = res.data.proxyUrl
      if (res.data.autoFillTitle !== undefined) settings.autoFillTitle = res.data.autoFillTitle
      if (res.data.autoSaveDraft !== undefined) settings.autoSaveDraft = res.data.autoSaveDraft
      if (res.data.autoSaveInterval !== undefined) settings.autoSaveInterval = res.data.autoSaveInterval
      if (res.data.accountCheckMode !== undefined) settings.accountCheckMode = res.data.accountCheckMode
      if (res.data.storage) {
        settings.storage = { ...settings.storage, ...res.data.storage }
      }
      if (res.data.accessTokenSet !== undefined) {
        settings.accessTokenSet = res.data.accessTokenSet
      }
      if (res.data.feedbackEmail !== undefined) {
        settings.feedbackEmail = res.data.feedbackEmail
        // 同步到 localStorage 让非设置页也能快速判断 email 是否已配置
        localStorage.setItem('global_user_email', settings.feedbackEmail || '')
      }
      // 把 disabledPlatforms(JSON 字符串数组)同步到 app store
      // 注意:后端 GET 不自动反序列化此字段,前端需手动 JSON.parse
      if (res.data.disabledPlatforms !== undefined && res.data.disabledPlatforms !== null && res.data.disabledPlatforms !== '') {
        try {
          const parsed: unknown = typeof res.data.disabledPlatforms === 'string'
            ? JSON.parse(res.data.disabledPlatforms)
            : res.data.disabledPlatforms
          appStore.disabledPlatforms = Array.isArray(parsed) ? parsed : []
        } catch (e: unknown) {
          console.warn('解析 disabledPlatforms 失败:', e)
          appStore.disabledPlatforms = []
        }
      } else {
        appStore.disabledPlatforms = []
      }
    }
  } catch (e: unknown) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    const res = (await settingsApi.updateSettings({
      proxyUrl: settings.proxyUrl,
      autoFillTitle: settings.autoFillTitle,
      autoSaveDraft: settings.autoSaveDraft,
      autoSaveInterval: settings.autoSaveInterval,
      accountCheckMode: settings.accountCheckMode,
      storage: settings.storage,
      feedbackEmail: settings.feedbackEmail,
    })) as ApiResponse
    if (res.code === 200) {
      // 同步到 Pinia store + localStorage(之前漏了这三项,导致开关不生效)
      appStore.setAutoFillTitle(settings.autoFillTitle)
      appStore.setAutoSaveDraft(settings.autoSaveDraft)
      appStore.setAutoSaveInterval(settings.autoSaveInterval)
      appStore.setAccountCheckMode(settings.accountCheckMode)
      localStorage.setItem('global_user_email', settings.feedbackEmail || '')
      ElMessage.success('设置已保存')
    } else {
      ElMessage.error(res.msg || '保存失败')
    }
  } catch (e: unknown) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 访问令牌：保存/清除（写入 settings 表 + 同步 localStorage 让请求拦截器携带）
const saveToken = async (token: string) => {
  const res = (await settingsApi.updateSettings({ access_token: token })) as ApiResponse
  if (res.code === 200) {
    localStorage.setItem('access_token', token)
    settings.accessTokenSet = true
    ElMessage.success('访问令牌已启用（本浏览器自动携带）')
  } else {
    ElMessage.error(res.msg || '保存失败')
    throw new Error(res.msg || '保存失败')
  }
}

const clearToken = async () => {
  const res = (await settingsApi.updateSettings({ access_token: '' })) as ApiResponse
  if (res.code === 200) {
    localStorage.removeItem('access_token')
    settings.accessTokenSet = false
    ElMessage.success('访问令牌已清除')
  } else {
    ElMessage.error(res.msg || '清除失败')
  }
}

onMounted(() => {
  fetchSettings()
  fetchSystemInfo()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.settings-page {
  padding: 0 28px;

  .page-title {
    font-size: 24px;
    font-weight: 600;
    color: $text-primary;
    margin: 0 0 8px 0;
  }

  .page-subtitle {
    font-size: 14px;
    color: $text-secondary;
    margin: 0 0 $spacing-lg 0;
  }

  .settings-card {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: $spacing-lg;
    margin-bottom: $spacing-md;

    .card-title {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 16px;
      font-weight: 600;
      color: $text-primary;
      margin: 0 0 $spacing-lg 0;
      padding-bottom: $spacing-sm;
      border-bottom: 1px solid $border;

      .title-icon {
        width: 20px;
        height: 20px;
        color: $text-secondary;
      }
    }

    .setting-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 0;

      &:not(:last-child) {
        border-bottom: 1px solid $border-light;
      }

      .setting-info {
        display: flex;
        flex-direction: column;
        gap: 4px;
        flex: 1;

        .setting-label {
          font-size: 14px;
          color: $text-primary;
          font-weight: 500;
        }

        .setting-desc {
          font-size: 12px;
          color: $text-muted;
          line-height: 1.5;
        }
      }

      .setting-control {
        flex-shrink: 0;
        margin-left: $spacing-lg;
        display: flex;
        align-items: center;
        gap: 12px;
      }
    }
  }

  // ── Tech stack section ──
  .tech-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: $spacing-lg;

    @media (max-width: 768px) {
      grid-template-columns: 1fr;
    }

    .tech-section {
      .version-badge {
        display: inline-flex;
        align-items: center;
        padding: 8px 20px;
        border-radius: 8px;
        background: $gradient-brand;
        color: #fff;
        font-size: 18px;
        font-weight: 700;
        font-family: 'Fira Code', monospace;
        letter-spacing: 0.5px;
      }

      .tech-section-title {
        font-size: 12px;
        font-weight: 600;
        color: $text-muted;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin: 0 0 $spacing-sm 0;
      }

      .tech-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid $border-light;

        &:last-child {
          border-bottom: none;
        }

        .tech-name {
          font-size: 14px;
          color: $text-primary;
        }

        .tech-version {
          font-size: 13px;
          color: $text-muted;
          font-family: 'Fira Code', monospace;
        }
      }
    }
  }

  .save-bar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 16px;
    padding: $spacing-lg 0;

    .save-btn {
      padding: 10px 32px;
      border: none;
      border-radius: $radius-base;
      font-size: 14px;
      font-weight: 500;
      color: #fff;
      background: $gradient-brand;
      cursor: pointer;
      transition: opacity $transition-base;

      &:hover:not(:disabled) {
        opacity: 0.9;
      }

      &:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
    }
  }

  // Element Plus overrides for dark theme consistency
  :deep(.el-input__wrapper),
  :deep(.el-select__wrapper),
  :deep(.el-input-number) {
    background-color: $bg-surface;
    box-shadow: 0 0 0 1px $border inset;
  }

  :deep(.el-input__inner),
  :deep(.el-select__placeholder),
  :deep(.el-input-number .el-input__inner) {
    color: $text-primary;
  }
}
</style>
