<template>
  <div class="dashboard">
    <!-- Page title area -->
    <h1 class="page-title">仪表盘</h1>
    <p class="page-subtitle">数据概览与快捷操作</p>

    <!-- 4 Stat cards row -->
    <div class="stat-cards">
      <StatCard
        variant="purple"
        :value="accountStats.total"
        label="账号总数"
        :details="[
          { label: '正常', value: accountStats.normal },
          { label: '异常', value: accountStats.abnormal },
        ]"
      >
        <template #icon>
          <el-icon><User /></el-icon>
        </template>
        <template #extra>
          <button class="batch-check-btn" @click="handleBatchCheck" :disabled="isChecking">
            <el-icon v-if="isChecking" class="is-loading"><Loading /></el-icon>
            <template v-else>
              <el-icon><Refresh /></el-icon>
              批量检查
            </template>
          </button>
        </template>
      </StatCard>

      <StatCard
        variant="blue"
        :value="platformStats.total"
        label="已接入平台"
      >
        <template #icon>
          <el-icon><Platform /></el-icon>
        </template>
        <template #bottom>
          <!-- 参考 DraftBox.channels 跑马灯: 溢出时横向滚动 -->
          <div class="platform-channels">
            <div
              class="channels-track"
              :class="{ 'channels-marquee': platformOverflow }"
              ref="platformTrackRef"
            >
              <span
                v-for="p in sortedPlatforms"
                :key="p.id"
                class="channel-tag"
                :class="{ 'is-active': p.count > 0 }"
              >
                <img
                  v-if="getPlatformLogo(p.key)"
                  :src="getPlatformLogo(p.key) || undefined"
                  :alt="p.name"
                  class="channel-icon"
                />
                <span class="channel-name">{{ p.name }}</span>
                <span class="channel-count">{{ p.count }}</span>
              </span>
            </div>
          </div>
        </template>
      </StatCard>

      <StatCard
        variant="cyan"
        :value="contentStats.total"
        label="素材总数"
        :details="[
          { label: '视频', value: contentStats.videos },
          { label: '图片', value: contentStats.images },
          { label: '其他', value: contentStats.others },
        ]"
      >
        <template #icon>
          <el-icon><Document /></el-icon>
        </template>
      </StatCard>

      <StatCard
        variant="green"
        value="—"
        label="今日发布"
        :details="[{ label: '成功率', value: '—' }]"
      >
        <template #icon>
          <el-icon><Upload /></el-icon>
        </template>
      </StatCard>
    </div>

    <!-- Quick actions row -->
    <div class="quick-actions">
      <QuickActionCard
        variant="purple"
        title="快速发布"
        desc="发布内容到各平台"
        route="/publish-center"
        @navigate="navigateTo"
      >
        <template #icon>
          <el-icon><Upload /></el-icon>
        </template>
      </QuickActionCard>

      <QuickActionCard
        variant="blue"
        title="上传素材"
        desc="上传和管理视频素材"
        route="/material-management"
        @navigate="navigateTo"
      >
        <template #icon>
          <el-icon><Document /></el-icon>
        </template>
      </QuickActionCard>

      <QuickActionCard
        variant="cyan"
        title="系统设置"
        desc="配置系统参数和选项"
        route="/settings"
        @navigate="navigateTo"
      >
        <template #icon>
          <el-icon><Setting /></el-icon>
        </template>
      </QuickActionCard>

      <QuickActionCard
        variant="green"
        title="账号管理"
        desc="管理所有平台账号"
        route="/account-management"
        @navigate="navigateTo"
      >
        <template #icon>
          <el-icon><UserFilled /></el-icon>
        </template>
      </QuickActionCard>
    </div>

    <!-- Recent materials table -->
    <div class="materials-card">
      <div class="materials-header">
        <h2>最近素材</h2>
        <a class="view-all-link" @click="navigateTo('/material-management')">查看全部</a>
      </div>

      <el-table
        :data="recentMaterials"
        style="width: 100%"
        v-loading="loading"
        :header-cell-style="{ background: 'transparent', borderBottom: `1px solid ${borderColor}` }"
        class="materials-table"
      >
        <el-table-column prop="original_filename" label="文件名" min-width="260">
          <template #default="scope">
            <span class="filename-cell">{{ scope.row.original_filename }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="file_size" label="大小" width="120">
          <template #default="scope">
            <span class="size-cell">{{ (scope.row.file_size / 1024 / 1024).toFixed(2) }} MB</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="scope">
            <span
              class="type-tag"
              :class="{
                'type-video': getFileType(scope.row.file_type) === '视频',
                'type-image': getFileType(scope.row.file_type) === '图片',
                'type-other': getFileType(scope.row.file_type) === '其他'
              }"
            >
              {{ getFileType(scope.row.file_type) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="upload_time" label="上传时间" width="200">
          <template #default="scope">
            <span class="time-cell">{{ scope.row.upload_time }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && recentMaterials.length === 0" class="empty-state">
        暂无素材数据
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 表格边框色（CSS 变量引用，随主题切换）
const borderColor = 'var(--border)'

import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { User, Platform, UserFilled, Document, Upload, Loading, Refresh, Setting } from '@element-plus/icons-vue'
import StatCard from '@/components/StatCard.vue'
import QuickActionCard from '@/components/QuickActionCard.vue'
import { ElMessage } from 'element-plus'
import { accountApi } from '@/api/account'
import { materialsApi } from '@/api/materials'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import {
  platformList, platformNameToKey, getPlatformByKey,
} from '@/config/platforms'
import { type ApiResponse } from '@/utils/request'

interface AccountItem {
  id: number | string
  type: string
  filePath: string
  name: string
  status: string
  platform: string
  avatar: string
  fans: number
  likes: number
  follows: number
  stats: unknown[]
  tags: unknown[]
}

interface MaterialItem {
  id: number | string
  original_filename: string
  file_type: 'image' | 'video' | string
  file_size?: number
  upload_time?: string
}

interface MaterialListResponse {
  items?: MaterialItem[]
  total?: number
}

interface PlatformStats {
  total: number
  [cssClass: string]: number
}

interface SortedPlatform {
  id: number
  key: string
  name: string
  count: number
}

const router = useRouter()
const accountStore = useAccountStore()
const appStore = useAppStore()
const loading = ref(false)
const isChecking = ref(false)

// 批量检查账号
const handleBatchCheck = async () => {
  if (isChecking.value) return
  isChecking.value = true
  try {
    const res = (await accountApi.getValidAccounts()) as ApiResponse<AccountItem[]>
    if (res.code === 200 && res.data) {
      accountStore.setAccounts(res.data)
      ElMessage.success('账号检查完成')
    } else {
      ElMessage.error(res.msg || '检查失败')
    }
  } catch (error) {
    console.error('批量检查失败:', error)
    ElMessage.error('批量检查失败')
  } finally {
    isChecking.value = false
  }
}

// 账号统计数据 - 从真实数据计算
const accountStats = computed(() => {
  const accounts = accountStore.accounts as AccountItem[]
  const normal = accounts.filter(a => a.status === '正常').length
  const abnormal = accounts.filter(a => a.status !== '正常' && a.status !== '验证中').length
  return {
    total: accounts.length,
    normal,
    abnormal
  }
})

// 平台统计数据 - 从真实数据计算
const platformStats = computed<PlatformStats>(() => {
  const accounts = accountStore.accounts as AccountItem[]
  const counts: Record<string, number> = {}
  platformList.forEach(p => {
    counts[p.cssClass] = accounts.filter(a => a.platform === p.name).length
  })
  // 统计有账号的平台数量
  const total = platformList.filter(p => counts[p.cssClass] > 0).length
  return { total, ...counts }
})

// 已接入平台列表 — 参考 DraftBox.channels 风格:
// 有账号的平台排前面 + count 降序,展示全部 15 个平台
const sortedPlatforms = computed<SortedPlatform[]>(() => {
  return platformList
    .map(p => ({
      id: p.id,
      key: p.key,
      name: p.name,
      count: accountStore.accounts.filter(a => a.platform === p.name).length,
    }))
    .sort((a, b) => b.count - a.count || a.id - b.id)
})

// 平台 chip 溢出检测 — 触发跑马灯滚动
const platformTrackRef = ref<HTMLElement | null>(null)
const platformOverflow = ref(false)
let platformResizeObserver: ResizeObserver | null = null

function detectPlatformOverflow() {
  const el = platformTrackRef.value
  if (!el) return
  // 父容器宽度 = el.parentElement.clientWidth
  platformOverflow.value = el.scrollWidth > (el.parentElement?.clientWidth ?? 0) + 1
}

onMounted(() => {
  fetchDashboardData()
  nextTick(() => {
    detectPlatformOverflow()
    if (typeof ResizeObserver !== 'undefined' && platformTrackRef.value) {
      platformResizeObserver = new ResizeObserver(detectPlatformOverflow)
      platformResizeObserver.observe(platformTrackRef.value)
      // 父容器 resize 也要监听(窗口缩放/侧栏展开)
      const parent = platformTrackRef.value.parentElement
      if (parent) platformResizeObserver.observe(parent)
    }
  })
})

onBeforeUnmount(() => {
  if (platformResizeObserver) {
    platformResizeObserver.disconnect()
    platformResizeObserver = null
  }
})

// 复用 platforms.js 的 getPlatformLogo (按 key 查 logo)
function getPlatformLogo(platformKey: string | null): string | null {
  return getPlatformByKey(platformKey ?? '')?.logo || null
}

// 素材统计数据 - 从 file_type 字段直接统计
const contentStats = computed(() => {
  const materials = appStore.materials as MaterialItem[]
  const videos = materials.filter(m => m.file_type === 'video').length
  const images = materials.filter(m => m.file_type === 'image').length
  return {
    total: materials.length,
    videos,
    images,
    others: materials.length - videos - images
  }
})

// 最近上传的素材（最多显示5条）
const recentMaterials = computed<MaterialItem[]>(() => {
  return [...(appStore.materials as MaterialItem[])]
    .sort((a, b) => new Date(b.upload_time || '').getTime() - new Date(a.upload_time || '').getTime())
    .slice(0, 5)
})

// 获取文件类型
const FILE_TYPE_MAP: Record<string, string> = { video: '视频', image: '图片' }
const getFileType = (fileType: string): string => FILE_TYPE_MAP[fileType] || '其他'

// 导航到指定路由
const navigateTo = (path: string) => {
  router.push(path)
}

// 加载数据
const fetchDashboardData = async () => {
  loading.value = true
  try {
    // 并行获取账号和素材数据
    const [accountRes, materialRes] = await Promise.allSettled([
      accountApi.getAccounts() as Promise<ApiResponse<AccountItem[]>>,
      materialsApi.list({ page_size: 200 }) as Promise<ApiResponse<MaterialListResponse>>
    ])

    if (accountRes.status === 'fulfilled' && accountRes.value.code === 200) {
      accountStore.setAccounts(accountRes.value.data ?? [])
    }
    if (materialRes.status === 'fulfilled' && materialRes.value.code === 200) {
      appStore.setMaterials(materialRes.value.data?.items || [])
    }
  } catch (error) {
    console.error('获取仪表盘数据失败:', error)
  } finally {
    loading.value = false
  }
}

</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.dashboard {
  // Page title area
  padding: 0 28px;

  .page-title {
    font-size: 26px;
    font-weight: 700;
    color: $text-primary;
    margin: 0;
    letter-spacing: -0.5px;
  }

  .page-subtitle {
    font-size: 14px;
    color: $text-muted;
    margin: 4px 0 24px;
  }

  // ========== Stat Cards ==========
  .stat-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    min-width: 0;
  }

  // stat-card 外壳样式已迁移至 components/StatCard.vue
  // 以下为 stat-card 内由父组件传入的 slot 内容样式

  // 批量检查按钮（紫色卡 #extra slot 内容）
  .batch-check-btn {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 6px 14px;
    border: 1px solid rgba($success-color, 0.3);
    border-radius: 8px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all $transition-base;
    background: rgba($success-color, 0.1);
    color: $success-color;
    white-space: nowrap;
    flex-shrink: 0;

    .el-icon {
      font-size: 14px;
    }

    &:hover:not(:disabled) {
      background: rgba($success-color, 0.2);
      border-color: rgba($success-color, 0.5);
      transform: translateY(-1px);
    }

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    &.is-loading .el-icon {
      animation: rotate 1s linear infinite;
    }
  }

  // 已接入平台 — 参考 DraftBox.channels 跑马灯布局（蓝色卡 #bottom slot 内容）
  // 关键: 容器必须 max-width: 100% 约束 + track 用 flex (不是 inline-flex)
  // 否则 inline-flex track 会按内容宽度撑开, 把 .stat-card 撑爆
  .platform-channels {
    overflow: hidden;
    max-width: 100%;
    padding: 2px 0;
    // 进一步防御: 容器本身是 block, 继承 .stat-bottom 的 100% 宽度
  }
  .channels-track {
    display: flex;
    flex-wrap: nowrap;       // 强制单行, 不要换行
    gap: 6px;
    max-width: 100%;
    min-width: 0;            // 关键: 阻止 flex 子项 min-width:auto 撑开
    // white-space 不需要: flex-wrap: nowrap 已经保证
  }
  .channels-marquee {
    animation: dashboard-marquee-scroll 12s linear infinite;
  }
  .channel-tag {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    padding: 3px 9px;
    border-radius: 999px;
    flex-shrink: 0;
    background: rgba($overlay-rgb, 0.06);
    color: $text-muted;
    border: 1px solid transparent;
    transition: all $transition-base;

    .channel-icon {
      width: 14px;
      height: 14px;
      border-radius: 3px;
      object-fit: contain;
    }
    .channel-name {
      color: inherit;
    }
    .channel-count {
      font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', ui-monospace, monospace;
      font-weight: 600;
      font-size: 11px;
      padding: 0 5px;
      border-radius: 8px;
      background: rgba($overlay-rgb, 0.08);
      color: $text-secondary;
      min-width: 18px;
      text-align: center;
    }

    // 有账号的平台: 高亮品牌色
    &.is-active {
      background: rgba($brand-start, 0.1);
      color: $text-primary;
      border-color: rgba($brand-start, 0.25);

      .channel-count {
        background: rgba($brand-start, 0.25);
        color: #fff;
      }
    }
  }

  @keyframes dashboard-marquee-scroll {
    0% { transform: translateX(0); }
    100% { transform: translateX(-50%); }
  }

  // ========== Quick Actions ==========
  .quick-actions {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-top: 24px;
  }

  // action-card 样式已迁移至 components/QuickActionCard.vue

  // ========== Materials Table ==========
  .materials-card {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: 24px;
    margin-top: 24px;

    .materials-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;

      h2 {
        font-size: 18px;
        font-weight: 600;
        color: $text-primary;
        margin: 0;
      }

      .view-all-link {
        font-size: 14px;
        color: $brand-start;
        cursor: pointer;
        transition: $transition-base;

        &:hover {
          color: $brand-end;
        }
      }
    }

    .materials-table {
      --el-table-bg-color: transparent;
      --el-table-tr-bg-color: transparent;
      --el-table-header-bg-color: transparent;
      --el-table-row-hover-bg-color: rgba($overlay-rgb, 0.03);
      --el-table-border-color: #{$border};
      --el-table-text-color: #{$text-secondary};
      --el-table-header-text-color: #{$text-muted};

      :deep(.el-table__inner-wrapper) {
        &::before {
          display: none;
        }
      }

      :deep(th.el-table__cell) {
        background: transparent !important;
        font-weight: 500;
        font-size: 13px;
        border-bottom: 1px solid $border;
      }

      :deep(td.el-table__cell) {
        border-bottom: 1px solid rgba($overlay-rgb, 0.04);
      }

      :deep(.el-table__empty-block) {
        background: transparent;
      }
    }

    .filename-cell {
      color: $text-primary;
      font-weight: 500;
    }

    .size-cell {
      color: $text-secondary;
    }

    .time-cell {
      color: $text-secondary;
      font-size: 13px;
    }

    .type-tag {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;

      &.type-video {
        color: $accent-green;
        background: rgba($accent-green, 0.12);
      }

      &.type-image {
        color: $accent-amber;
        background: rgba($accent-amber, 0.12);
      }

      &.type-other {
        color: $text-muted;
        background: rgba($overlay-rgb, 0.06);
      }
    }

    .empty-state {
      text-align: center;
      color: $text-muted;
      padding: 40px 0;
      font-size: 14px;
    }
  }
}
</style>
