<template>
  <div class="account-management">
    <div class="page-header">
      <div class="header-content">
        <div class="header-text">
          <h1>账号管理</h1>
          <p class="page-subtitle">管理所有平台账号</p>
        </div>
        <div class="header-actions">
          <el-button type="primary" class="add-btn" @click="handleAddAccount">
            <el-icon><Plus /></el-icon>
            添加账号
          </el-button>
          <el-button class="add-btn import-btn" @click="importDialogVisible = true">
            <el-icon><Upload /></el-icon>
            导入用户
          </el-button>
        </div>
      </div>
    </div>

    <!-- 平台筛选标签 -->
    <div class="platform-tabs">
      <button
        v-for="tab in filterOptions"
        :key="tab.value"
        :class="['tab-item', { active: activeTab === tab.value }]"
        @click="activeTab = tab.value"
      >
        <span class="tab-label">{{ tab.label }}</span>
        <span v-if="tab.count" class="tab-count">{{ tab.count }}</span>
      </button>
    </div>

    <!-- 搜索栏 -->
    <div class="search-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索名称或账号..."
        prefix-icon="Search"
        clearable
        class="search-input"
      />
      <el-button class="refresh-btn" @click="fetchAccountsQuick" :loading="appStore.isAccountRefreshing">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      <el-button class="check-all-btn" @click="fetchAccounts" :loading="appStore.isAccountRefreshing">
        <el-icon v-if="!appStore.isAccountRefreshing"><Loading /></el-icon>
        批量检查
      </el-button>
      <el-button class="batch-tag-btn" @click="batchTagDialogVisible = true">
        <el-icon><CollectionTag /></el-icon>
        批量设置标签
      </el-button>
    </div>

    <!-- 标签筛选 -->
    <div v-if="tagFilterOptions.length > 0" class="tag-filter-bar">
      <button
        :class="['tag-filter-item', { active: !activeTagId }]"
        @click="activeTagId = null"
      >全部标签</button>
      <button
        v-for="tag in tagFilterOptions"
        :key="tag.id"
        :class="['tag-filter-item', { active: activeTagId === tag.id }]"
        @click="activeTagId = activeTagId === tag.id ? null : tag.id"
      >
        <span class="tag-dot" :style="{ background: tag.color }"></span>
        {{ tag.name }}
      </button>
    </div>

    <!-- 账号卡片列表 -->
    <div v-if="filteredAccounts.length > 0" class="account-grid">
      <AccountCard
        v-for="account in filteredAccounts"
        :key="account.id"
        :account="account"
        :checking-ids="checkingIds"
        :syncing-ids="syncingIds"
        :tag-overflow-map="tagOverflowMap"
        :disabled="isAccountDisabled(account)"
        @check="handleCheckAccount"
        @sync="handleSyncProfile"
        @relogin="handleReLogin"
        @creator="handleOpenCreatorCenter"
        @delete="handleDelete"
        @remove-tag="handleRemoveAccountTag"
        @tag-changed="onTagChanged"
      />
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <div class="empty-content">
        <el-icon class="empty-icon"><Folder /></el-icon>
        <h3>{{ searchKeyword ? '未找到匹配账号' : '暂无账号数据' }}</h3>
        <p>{{ searchKeyword ? '请尝试其他关键词搜索' : '点击上方"添加账号"开始绑定你的第一个平台账号' }}</p>
        <el-button v-if="!searchKeyword" type="primary" @click="handleAddAccount">
          <el-icon><Plus /></el-icon>
          添加账号
        </el-button>
      </div>
    </div>

    <!-- 添加/重新登录账号对话框 -->
    <LoginDialog
      v-model="loginDialogVisible"
      :mode="loginMode"
      :account="reloginAccount"
      @success="onLoginSuccess"
      @fail="onLoginFail"
    />

    <!-- 批量设置标签对话框 -->
    <BatchTagDialog
      v-model="batchTagDialogVisible"
      @done="onBatchTagDone"
    />

    <!-- 批量检查对话框（复用发布前检查的 4 阶段进度 + 失效自动重登） -->
    <PrePublishCheckDialog
      ref="prePublishCheckRef"
      v-model="prePublishCheckVisible"
      mode="account-check"
    />

    <!-- 导入用户对话框：粘贴 cookie 字符串 → 后端 4 步进度 -->
    <ImportAccountDialog v-model="importDialogVisible" @success="fetchAccountsQuick" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { Refresh, Loading, Plus, Folder, CollectionTag, Upload, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { accountApi } from '@/api/account'
import { useAccountStore, type AccountRow } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { http, type ApiResponse } from '@/utils/request'
import { platformList, platformNameToId, platformNameToKey, platformCssMap, getPlatformByName } from '@/config/platforms'
import LoginDialog from '@/components/LoginDialog.vue'
import PrePublishCheckDialog from '@/components/PrePublishCheckDialog.vue'
import AccountCard from '@/components/AccountCard.vue'
import ImportAccountDialog from '@/components/ImportAccountDialog.vue'
import { getPlatformColor, getPlatformBg, getPlatformLogo, type StatItem, type AccountItem, type TagItem } from '@/components/accountCardShared'
import BatchTagDialog from '@/components/BatchTagDialog.vue'
import { getErrorMessage } from '@/utils/error'

/** 平台筛选 tab */
interface FilterOption {
  label: string
  value: string
  count: number
}





/** 编辑账号表单 */
interface AccountForm {
  id: number | null
  name: string
  platform: string
  status: string
}

const accountStore = useAccountStore()
const appStore = useAppStore()

/** 平台是否已被加入黑名单（account.platform 是中文名,需先转为 key） */
const isAccountDisabled = (account: AccountItem) => {
  const key = platformNameToKey[account.platform]
  return !!(key && appStore.isPlatformDisabled(key))
}

const activeTagId = ref<number | string | null>(null)
// 哪些账号的标签溢出(决定是否跑马灯):key=accountId
const tagOverflowMap = ref<Record<number, boolean>>({})

const tagFilterOptions = computed<TagItem[]>(() => accountStore.allTags as TagItem[])

// 检测每张卡片标签行是否溢出,溢出时启用跑马灯
function checkTagOverflow() {
  nextTick(() => {
    const rows = document.querySelectorAll('.account-tags-viewport')
    const next: Record<number, boolean> = {}
    rows.forEach(viewport => {
      const track = viewport.querySelector('.account-tags-track')
      const card = viewport.closest('.account-card') as HTMLElement | null
      const id = Number(card?.dataset?.accountId)
      if (id && track) {
        next[id] = track.scrollWidth > viewport.clientWidth + 1
      }
    })
    tagOverflowMap.value = next
  })
}

watch(() => accountStore.accounts, () => {
  checkTagOverflow()
}, { deep: true })

let tagResizeObserver: ResizeObserver | null = null

onMounted(() => {
  fetchAccountsQuick()
  accountStore.loadTags()
  nextTick(() => {
    checkTagOverflow()
    tagResizeObserver = new ResizeObserver(() => checkTagOverflow())
    const observer = tagResizeObserver
    if (observer) document.querySelectorAll('.account-tags-viewport').forEach(el => observer.observe(el))
  })
})

onBeforeUnmount(() => {
  tagResizeObserver?.disconnect()
})

async function onTagChanged() {
  await fetchAccountsQuick()
}

async function handleRemoveAccountTag(account: AccountItem, tag: TagItem) {
  const remaining = (account.tags || []).filter(t => t.id !== tag.id).map(t => t.id)
  try {
    const res = (await accountApi.setAccountTags(account.id, remaining)) as ApiResponse
    if (res.code === 200) {
      await fetchAccountsQuick()
      ElMessage.success(`已从「${account.name}」移除标签「${tag.name}」`)
    } else {
      ElMessage.error(res.msg || '移除失败')
    }
  } catch (e) {
    console.error('移除标签失败:', e)
    ElMessage.error('移除标签失败')
  }
}

const activeTab = ref('all')
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(12)

const filterOptions = computed<FilterOption[]>(() => {
  const counts: Record<string, number> = {}
  ;(accountStore.accounts as AccountItem[]).forEach(a => {
    counts[a.platform] = (counts[a.platform] || 0) + 1
  })
  return [
    { label: '全部', value: 'all', count: (accountStore.accounts as AccountItem[]).length },
    ...platformList.map(p => ({ label: p.name, value: p.name, count: counts[p.name] || 0 }))
  ].filter(opt => opt.value === 'all' || (opt.count && opt.count > 0))
})

const fetchAccountsQuick = async () => {
  try {
    const res = (await accountApi.getAccounts()) as ApiResponse<AccountRow[]>
    if (res.code === 200 && res.data) {
      accountStore.setAccounts(res.data)
    }
  } catch (error) {
    console.error('快速获取账号数据失败:', error)
  }
}

// 模板里用 ref 拿到 PrePublishCheckDialog 组件实例
const prePublishCheckRef = ref<InstanceType<typeof PrePublishCheckDialog> | null>(null)
const prePublishCheckVisible = ref(false)

const fetchAccounts = async () => {
  if (appStore.isAccountRefreshing) return
  if (!(accountStore.accounts as AccountItem[]).length) {
    ElMessage.warning('暂无账号可检查')
    return
  }
  appStore.setAccountRefreshing(true)
  // 复用发布前检查的 4 阶段进度弹窗（与发布流程交互一致）:
  // 1) checking → 进度条 + 卡片实时状态
  // 2) all-valid → 全部正常，1.2s 后自动关闭
  // 3) fixing   → 失效账号自动打开 SSE 登录
  // 4) done     → 全部修复完成，1.2s 后自动关闭
  try {
    const dialog = prePublishCheckRef.value
    if (!dialog) return
    const allValid = await dialog.open(accountStore.accounts as AccountItem[])
    // dialog 内部已逐张更新 accountStore；这里再拉一次最新状态保证 UI 同步
    await fetchAccountsQuick()
    if (allValid && appStore.isFirstTimeAccountManagement) {
      appStore.setAccountManagementVisited()
    }
  } catch (error) {
    console.error('批量检查失败:', error)
    ElMessage.error('批量检查失败')
  } finally {
    appStore.setAccountRefreshing(false)
  }
}


const filteredAccounts = computed<AccountItem[]>(() => {
  let accounts: AccountItem[] = accountStore.accounts as AccountItem[]
  if (activeTab.value !== 'all') {
    accounts = accounts.filter(a => a.platform === activeTab.value)
  }
  if (activeTagId.value) {
    accounts = accounts.filter(a => a.tags?.some(t => t.id === activeTagId.value))
  }
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    accounts = accounts.filter(a => a.name.toLowerCase().includes(keyword))
  }
  return accounts
})

const paginatedAccounts = computed<AccountItem[]>(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredAccounts.value.slice(start, end)
})

watch([activeTab, searchKeyword], () => {
  currentPage.value = 1
})

const dialogVisible = ref(false)
const dialogType = ref<'add' | 'edit'>('add')
const accountFormRef = ref<FormInstance | null>(null)

const accountForm = reactive<AccountForm>({ id: null, name: '', platform: '', status: '正常' })

const rules: FormRules = {
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }]
}

const checkingIds = ref(new Set<number>())

// LoginDialog 弹窗控制
const loginDialogVisible = ref(false)
const loginMode = ref<'add' | 'relogin'>('add')        // 'add' | 'relogin'
const reloginAccount = ref<AccountItem | null>(null)

// ── 导入用户（cookie 字符串）弹窗控制 ──────────────────────────
const importDialogVisible = ref(false)
// ────────────────────────────────────────────────────────────

const handleCheckAccount = async (row: AccountItem) => {
  checkingIds.value.add(row.id)
  try {
    const res = (await http.get('/checkAccount', { id: row.id })) as ApiResponse<{ valid: boolean; status?: string }>
    if (res.code === 200 && res.data) {
      const { valid, status } = res.data
      accountStore.updateAccount(row.id, { ...row, status: valid ? '正常' : '异常' })
      ElMessage({ type: valid ? 'success' : 'warning', message: res.msg })
    } else {
      ElMessage.error(res.msg || '检查失败')
    }
  } catch (e) {
    ElMessage.error('检查请求失败')
  } finally {
    checkingIds.value.delete(row.id)
  }
}

const handleAddAccount = () => {
  loginMode.value = 'add'
  reloginAccount.value = null
  loginDialogVisible.value = true
}

const handleEdit = (row: AccountItem) => {
  dialogType.value = 'edit'
  Object.assign(accountForm, { id: row.id, name: row.name, platform: row.platform, status: row.status })
  dialogVisible.value = true
}

const handleDelete = (row: AccountItem) => {
  ElMessageBox.confirm(`确定要删除账号 ${row.name} 吗？`, '警告', {
    confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
  }).then(async () => {
    try {
      const response = (await accountApi.deleteAccount(row.id)) as ApiResponse
      if (response.code === 200) {
        accountStore.deleteAccount(row.id)
        ElMessage({ type: 'success', message: '删除成功' })
      } else {
        ElMessage.error(response.msg || '删除失败')
      }
    } catch (error) {
      console.error('删除账号失败:', error)
      ElMessage.error('删除账号失败')
    }
  }).catch(() => {})
}

const handleDownloadCookie = (row: AccountItem) => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || window.location.origin
  const downloadUrl = `${baseUrl}/downloadCookie?filePath=${encodeURIComponent(row.filePath)}`
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = `${row.name}_cookie.json`
  link.target = '_blank'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

const handleUploadCookie = (row: AccountItem) => {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.style.display = 'none'
  document.body.appendChild(input)

  input.onchange = async (event) => {
    const file = (event.target as HTMLInputElement).files?.[0]
    if (!file) return
    if (!file.name.endsWith('.json')) {
      ElMessage.error('请选择JSON格式的Cookie文件')
      document.body.removeChild(input)
      return
    }
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('id', String(row.id))
      formData.append('platform', row.platform)
      await http.upload('/uploadCookie', formData)
      ElMessage.success('Cookie文件上传成功')
      fetchAccounts()
    } catch (error) {
      ElMessage.error('Cookie文件上传失败')
    } finally {
      document.body.removeChild(input)
    }
  }
  input.click()
}

const handleReLogin = (row: AccountItem) => {
  if (isAccountDisabled(row)) return
  loginMode.value = 'relogin'
  reloginAccount.value = row
  loginDialogVisible.value = true
}

const syncingIds = reactive(new Set<number>())

const handleSyncProfile = async (row: AccountItem) => {
    if (syncingIds.has(row.id)) return
    syncingIds.add(row.id)
    try {
      const res = (await accountApi.syncProfile(row.id)) as ApiResponse<{ name?: string; avatar?: string; stats?: StatItem[] }>
      if (res.code === 200 && res.data) {
        // 新接口返回 {name, avatar, stats: [{ICON, COUNT, NAME, SORT}, ...]}
        // 旧平台 stats 为 [] 时保留原值;新平台返回新数组时覆盖
        const newStats = Array.isArray(res.data.stats) ? res.data.stats : null
        accountStore.updateAccount(row.id, {
          id: row.id,
          name: res.data.name || row.name,
          avatar: res.data.avatar || row.avatar,
          stats: newStats !== null ? newStats : (row.stats || []),
        })
        ElMessage.success('资料同步成功')
      } else {
        ElMessage.error(res.msg || '同步失败')
      }
    } catch (error) {
      console.error('同步资料失败:', error)
      ElMessage.error('同步资料失败')
    } finally {
      syncingIds.delete(row.id)
    }
  }

// 账号运营数据(粉丝/获赞/关注)是否需要展示:任一 > 0 才显示

const handleOpenCreatorCenter = async (row: AccountItem) => {
  try {
    const res = (await http.post('/openCreatorCenter', { id: row.id })) as ApiResponse
    if (res.code === 200) {
      ElMessage.success('正在打开创作中心...')
    } else {
      ElMessage.error(res.msg || '打开失败')
    }
  } catch (error) {
    console.error('打开创作中心失败:', error)
    ElMessage.error('打开创作中心失败')
  }
}

// LoginDialog 回调:登录成功后刷新账号列表(后端 sync_profile 已写库)
const onLoginSuccess = ({ platform, accountId }: { platform: string; accountId?: number | string }) => {
  fetchAccountsQuick()
}

const onLoginFail = ({ platform, errMsg }: { platform: string; errMsg?: string }) => {
  console.warn(`登录失败 [${platform}]:`, errMsg)
}

// 批量设置标签
const batchTagDialogVisible = ref(false)
const onBatchTagDone = async () => {
  await accountStore.loadTags()
  await fetchAccountsQuick()
}

const submitAccountForm = () => {
  const formRef = accountFormRef.value
  if (!formRef) return
  formRef.validate(async (valid) => {
    if (valid) {
      try {
        const type = platformNameToId[accountForm.platform] || 1
        const res = (await accountApi.updateAccount({ id: accountForm.id, type, userName: accountForm.name })) as ApiResponse
        if (res.code === 200) {
          if (accountForm.id !== null) accountStore.updateAccount(accountForm.id, { id: accountForm.id, name: accountForm.name, platform: accountForm.platform, status: accountForm.status })
          ElMessage.success('更新成功')
          dialogVisible.value = false
          fetchAccountsQuick()
        } else {
          ElMessage.error(res.msg || '更新账号失败')
        }
      } catch (error) {
        console.error('更新账号失败:', error)
        ElMessage.error('更新账号失败')
      }
    }
  })
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.account-management {
  padding: 24px;
  width: 100%;
  max-width: none;
  margin: 0;
  box-sizing: border-box;

  .page-header {
    margin-bottom: 24px;

    .header-content {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }

    .header-actions {
      display: flex;
      gap: 12px;
      flex-shrink: 0;
    }

    h1 {
      font-size: 28px;
      font-weight: 700;
      color: $text-primary;
      margin: 0;
      letter-spacing: -0.5px;
      background: $gradient-brand;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .page-subtitle {
      margin: 8px 0 0;
      font-size: 14px;
      color: $text-muted;
      font-weight: 400;
    }

    .add-btn {
      background: $gradient-brand;
      border: none;
      padding: 10px 20px;
      font-weight: 600;
      border-radius: 10px;
      box-shadow: 0 4px 15px rgba($brand-start, 0.3);
      transition: all $transition-base;

      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba($brand-start, 0.4);
      }
    }

    /* 导入用户：次级按钮风格，不抢主按钮的视觉权重 */
    .add-btn.import-btn {
      background: rgba($overlay-rgb, 0.06);
      border: 1px solid rgba($overlay-rgb, 0.18);
      box-shadow: none;
      color: $text-primary;

      &:hover {
        background: rgba($overlay-rgb, 0.12);
        border-color: rgba($overlay-rgb, 0.3);
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
      }
    }
  }

  // Platform tabs
  .platform-tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
    flex-wrap: wrap;

    .tab-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      background: $bg-surface;
      border: 1px solid $border;
      border-radius: 10px;
      color: $text-secondary;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all $transition-base;

      &:hover {
        background: rgba($brand-start, 0.1);
        border-color: rgba($brand-start, 0.3);
        color: $text-primary;
      }

      &.active {
        background: rgba($brand-start, 0.15);
        border-color: $brand-start;
        color: $brand-start;
        font-weight: 600;
        box-shadow: 0 0 20px rgba($brand-start, 0.2);
      }

      .tab-count {
        background: rgba($overlay-rgb, 0.1);
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 12px;
      }

      &.active .tab-count {
        background: rgba($overlay-rgb, 0.2);
      }
    }
  }

  // Search bar
  .search-bar {
    display: flex;
    gap: 12px;
    margin-bottom: 24px;
    align-items: center;

    .search-input {
      flex: 1;
      max-width: 320px;

      :deep(.el-input__wrapper) {
        background: $bg-surface;
        border: 1px solid $border;
        border-radius: 10px;
        box-shadow: none;
        padding: 4px 16px;

        &:hover, &.is-focus {
          border-color: rgba($brand-start, 0.5);
          box-shadow: 0 0 0 3px rgba($brand-start, 0.1);
        }
      }
    }

    .refresh-btn, .check-all-btn, .batch-tag-btn {
      background: $bg-surface;
      border: 1px solid $border;
      border-radius: 10px;
      color: $text-secondary;
      padding: 8px 16px;
      transition: all $transition-base;

      &:hover {
        background: rgba($brand-start, 0.1);
        border-color: rgba($brand-start, 0.3);
        color: $text-primary;
      }
    }
  }

  .tag-filter-bar {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
    flex-wrap: wrap;

    .tag-filter-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: $bg-surface;
      border: 1px solid $border;
      border-radius: 8px;
      font-size: 13px;
      color: $text-secondary;
      cursor: pointer;
      transition: all $transition-base;

      &:hover { background: rgba($brand-start, 0.1); }
      &.active {
        background: rgba($brand-start, 0.15);
        border-color: $brand-start;
        color: $brand-start;
      }

      .tag-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }
    }
  }

  // Account grid
  .account-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 20px;
    margin-bottom: 24px;
    padding-bottom: 20px;
    overflow-y: visible;

    &::-webkit-scrollbar {
      width: 6px;
    }

    &::-webkit-scrollbar-track {
      background: transparent;
    }

    &::-webkit-scrollbar-thumb {
      background: $border;
      border-radius: 3px;
    }
  }

  // Account card
  .empty-state {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 300px;
    margin-bottom: 24px;

    .empty-content {
      text-align: center;
      padding: 48px;

      .empty-icon {
        font-size: 64px;
        color: $text-muted;
        margin-bottom: 16px;
      }

      h3 {
        font-size: 20px;
        font-weight: 600;
        color: $text-primary;
        margin: 0 0 8px;
      }

      p {
        font-size: 14px;
        color: $text-muted;
        margin: 0 0 24px;
      }
    }
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

</style>
