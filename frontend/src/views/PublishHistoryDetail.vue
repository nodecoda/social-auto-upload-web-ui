<template>
  <div class="publish-history-detail">
    <!-- 顶部导航条 -->
    <header class="page-header">
      <el-button link :icon="ArrowLeft" @click="goBack">返回</el-button>
      <div class="header-info">
        <h1 class="batch-title">{{ batch?.title || '加载中...' }}</h1>
        <span v-if="batch" class="status-tag" :class="`status-${batch.status}`">
          {{ statusLabel(batch.status) }}
        </span>
        <span v-if="batch?.created_at" class="header-time">{{ formatTime(batch.created_at) }}</span>
      </div>
    </header>

    <div class="detail-body">
      <!-- 左侧：账号栏 -->
      <aside v-if="batch" class="detail-sidebar">
        <AccountSidebar
          :mode="'readonly'"
          :account-groups="readonlyAccountGroups"
          :total-count="batchAccounts.length"
          :selected-platform="undefined"
          :selected-account-id="selectedAccountId"
          :expanded-groups="expandedGroups"
          :publish-account-ids="readonlyPublishAccountIds"
          :has-account-override="() => false"
          @toggle-group="toggleGroup"
          @select-account="selectAccount"
        />
      </aside>

      <!-- 右侧：主区域 -->
      <main class="detail-main" v-loading="loading">
        <!-- 5xx 重试条 -->
        <div v-if="error" class="error-bar">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ error }}</span>
          <el-button size="small" @click="fetchDetail">重试</el-button>
        </div>

        <!-- 空状态 -->
        <div v-else-if="!selectedItem" class="empty-state">
          <el-icon class="empty-icon"><DocumentRemove /></el-icon>
          <p>该批次暂无账号数据</p>
          <p v-if="batchAccounts.length === 0 && (batch?.account_count ?? 0) > 0" class="empty-hint">
            该批次的账号已被全部删除，请前往
            <router-link to="/account-management">账号管理</router-link>
            查看
          </p>
        </div>

        <template v-else>
          <!-- 1. 账号信息头 -->
          <DetailAccountHeader
            :item="selectedItem"
            :account="selectedAccount"
            :platform-config="currentPlatformConfig"
          />

          <!-- 2. 内容快照 -->
          <PublishSnapshot
            :item="selectedItem"
            :fallback-title="batch?.title"
            :fallback-description="batch?.description"
            :fallback-cover-url="batch?.cover_url"
          />

          <!-- 3. 数据统计 -->
          <section class="data-stats">
            <h3 class="section-title">数据统计</h3>
            <PublishStats />
          </section>

          <!-- 4. 批次元信息 -->
          <BatchMetaCard
            v-model:meta-open="metaOpen"
            :batch="batch"
            :account-count="batchAccounts.length"
          />
        </template>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, WarningFilled, DocumentRemove, CircleCloseFilled, Picture } from '@element-plus/icons-vue'
import { useAccountStore, type AccountRow } from '@/stores/account'
import { accountApi } from '@/api/account'
import { historyApi } from '@/api/v2'
import { getErrorMessage } from '@/utils/error'
import { platformList, getPlatformByKey } from '@/config/platforms'
import { type ApiResponse } from '@/utils/request'
import AccountSidebar from '@/components/AccountSidebar.vue'
import PublishSnapshot, { type BatchItem } from '@/components/PublishSnapshot.vue'
import PublishStats from '@/components/PublishStats.vue'
import DetailAccountHeader from '@/components/DetailAccountHeader.vue'
import BatchMetaCard from '@/components/BatchMetaCard.vue'
import { statusLabel, formatTime } from '@/components/publishHistoryShared'

interface HistoryBatch {
  id: string
  title: string
  status: string
  description?: string
  created_at?: string
  schedule_time?: string
  started_at?: string
  finished_at?: string
  cover_url?: string
  account_count?: number
  items: BatchItem[]
}

interface PlatformAccount {
  id: number | string
  name: string
  platform: string
  status: string
  avatar?: string
  [key: string]: unknown
}

interface AccountGroup {
  key: string
  name: string
  color: string
  logo?: string
  letter: string
  accounts: PlatformAccount[]
}

const route = useRoute()
const router = useRouter()
const accountStore = useAccountStore()

const batch = ref<HistoryBatch | null>(null)
const loading = ref(false)
const error = ref('')
const selectedAccountId = ref<number | string | null>(null)
const metaOpen = ref<string[]>([])
const expandedGroups = reactive(new Set<string>())
const readonlyPublishAccountIds = new Set<number | string>()  // 空 Set，AccountSidebar 内部不过滤

const batchAccounts = computed<PlatformAccount[]>(() => {
  if (!batch.value) return []
  return accountStore.accounts.filter((a: PlatformAccount) =>
    batch.value!.items.some(it => it.account_id === a.id)
  )
})

const readonlyAccountGroups = computed<AccountGroup[]>(() => {
  return platformList
    .map(p => ({
      key: p.key,
      name: p.name,
      logo: p.logo,
      color: p.color,
      letter: p.letter,
      accounts: batchAccounts.value.filter(a => a.platform === p.name),
    }))
    .filter(g => g.accounts.length > 0)
})

const selectedItem = computed<BatchItem | null>(() => {
  if (!batch.value || !selectedAccountId.value) return null
  return batch.value.items.find(it => it.account_id === selectedAccountId.value) || null
})

const selectedAccount = computed<PlatformAccount | null>(() => {
  if (!selectedItem.value) return null
  return accountStore.accounts.find((a: PlatformAccount) => a.id === selectedItem.value!.account_id) || null
})

const currentPlatformConfig = computed(() => {
  if (!selectedAccount.value) return null
  const key = platformList.find(p => p.name === selectedAccount.value!.platform)?.key
  return key ? getPlatformByKey(key) : null
})

function goBack() {
  router.push('/publish-history')
}

function toggleGroup(key: string) {
  if (expandedGroups.has(key)) expandedGroups.delete(key)
  else expandedGroups.add(key)
}

function selectAccount(account: PlatformAccount /*, group */) {
  selectedAccountId.value = account.id
}

async function fetchDetail() {
  error.value = ''
  loading.value = true
  try {
    const res = (await historyApi.getBatch(route.params.batchId as string)) as ApiResponse<HistoryBatch>
    // 拦截器只在 data.code === 200 时 resolve，否则 reject；到这里就是成功
    batch.value = res.data!
    // 默认选中：找第一个 account_id 在 store 里能找到的 item
    const firstValid = batch.value.items.find(it =>
      it.account_id != null &&
      accountStore.accounts.some((a: PlatformAccount) => a.id === it.account_id)
    )
    if (firstValid) selectedAccountId.value = firstValid.account_id
    // 展开所有有账号的组
    readonlyAccountGroups.value.forEach(g => expandedGroups.add(g.key))
  } catch (e) {
    // 拦截器已经 toast（4xx 用后端 msg，5xx 用通用文案）；这里只补行为
    const err = e as { response?: { status?: number }; message?: string }
    if (err?.response?.status === 404) {
      // 批次不存在 → 跳回列表
      router.replace('/publish-history')
    } else if (err?.response?.status != null && err.response.status >= 500) {
      // 服务端错误 → 主区域顶部红条 + 重试按钮
      error.value = '加载失败，请稍后重试'
    } else if (!err?.response) {
      // 网络错误
      error.value = '加载失败，请稍后重试'
    } else {
      // 其它 4xx（401/403 等）→ 红条
      error.value = getErrorMessage(err) || '加载失败'
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  // 串行：先加载账号 store，再拉详情
  try {
    if (accountStore.accounts.length === 0) {
      const res = (await accountApi.getAccounts()) as ApiResponse<AccountRow[]>
      accountStore.setAccounts(res.data || [])
    }
  } catch (e) {
    console.error('加载账号列表失败:', e)
  }
  await fetchDetail()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.publish-history-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: $bg-base;
  // 整体节奏：主区卡片间距 20px，卡片内 padding 20px，留白与卡片内文本密度平衡
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  height: 56px;
  padding: 0 24px;
  border-bottom: 1px solid $border;
  background: $bg-elevated;
  flex-shrink: 0;

  .header-info {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .batch-title {
    font-size: 16px;
    font-weight: 600;
    color: $text-primary;
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 400px;
    // 字距略紧，提升数据密集页的标题密度
    letter-spacing: -0.01em;
  }

  .header-time {
    font-size: 12px;
    color: $text-muted;
  }
}

.detail-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.detail-sidebar {
  width: 232px;
  flex-shrink: 0;
  overflow-y: auto;
  // 左侧栏与主区用 1px 透明 border 拉出节奏（与右侧圆角卡呼应）
  border-right: 1px solid $border-light;
}

.detail-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 20px 24px 28px;  // 顶部 20px 与 56px header 形成 8 倍数节奏
  display: flex;
  flex-direction: column;
  gap: 20px;  // 卡片间距：8 倍数节奏
}

.status-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;

  &.status-success, &.status-partial {
    background: rgba($accent-green, 0.15);
    color: #67c23a;
  }
  &.status-failed {
    background: rgba($danger-color, 0.15);
    color: #f56c6c;
  }
  &.status-running {
    background: rgba($info-color, 0.15);
    color: #409eff;
  }
  &.status-pending, &.status-cancelled {
    background: rgba(0, 0, 0, 0.06);
    color: $text-muted;
  }
}

// 5xx 错误降级红条：使用项目 danger 色 + 8px 圆角 + 浅红底 + 1px 红边
.error-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: rgba($danger-color, 0.1);
  border: 1px solid rgba($danger-color, 0.3);
  border-radius: 8px;
  color: #f56c6c;
  font-size: 14px;
  // 红条与下方卡片同节奏：margin-bottom 改为父级 gap 接管
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: $text-muted;
  text-align: center;
  gap: 8px;
  padding: 48px 16px;

  .empty-icon {
    font-size: 48px;
    opacity: 0.5;
  }

  p {
    margin: 0;
    font-size: 14px;
  }

  .empty-hint {
    font-size: 12px;
    a { color: $brand-start; text-decoration: none; }
    a:hover { text-decoration: underline; }
  }
}

// 1. 账号信息头：圆角 12px + 1px 边框 + 48px 头像，header 内部 16px gap


// 3. 数据统计：16/20 padding，标题与内容 12px 分隔
.data-stats {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: 16px 20px;

  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: $text-primary;
    margin: 0 0 12px;
    letter-spacing: -0.005em;
  }
}

// 4. 批次元信息折叠卡：左右 0/20 padding 配合 el-collapse-item 内部 padding 形成节奏

</style>
