<template>
  <div class="publish-history-page">
    <h1 class="page-title">发布历史</h1>
    <p class="page-subtitle">回顾所有发布记录</p>

    <!-- 3 Stat cards row -->
    <HistoryStatsCards :stats="stats" />

    <!-- Filter toolbar -->
    <HistoryFilterBar
      v-model:time-range="timeRange"
      v-model:type-filter="typeFilter"
      v-model:platform-filter="platformFilter"
      v-model:status-filter="statusFilter"
      :select-mode="selectMode"
      :batches-count="batches.length"
      :loading="loading"
      @change="handleFilterChange"
      @select-mode-toggle="toggleSelectMode"
      @refresh="fetchHistory"
    />

    <!-- Batch operations toolbar -->
    <HistoryBatchToolbar
      v-if="selectMode"
      :is-all-selected="isAllSelected"
      :is-indeterminate="isIndeterminate"
      :selection-size="selection.size"
      :total-count="batches.length"
      :is-deleting="isDeleting"
      @toggle-select-all="toggleSelectAll"
      @batch-delete="onBatchDelete"
      @exit-select-mode="toggleSelectMode"
    />

    <!-- 卡片网格 -->
    <div class="cards-grid" v-loading="loading">
      <div v-if="!loading && batches.length === 0" class="empty-state">
        <el-icon class="empty-icon"><Clock /></el-icon>
        <p>暂无发布记录</p>
      </div>
      <HistoryCard
        v-for="batch in batches"
        :key="batch.id"
        :batch="batch"
        :select-mode="selectMode"
        :selection="selection"
        @card-click="onCardClick"
        @toggle-selection="toggleSelection"
        @delete="confirmDelete"
      />
    </div>

    <!-- Pagination -->
    <div class="pagination-wrapper" v-if="total > 0">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
        background
      />
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type CheckboxValueType } from 'element-plus'
import { Clock } from '@element-plus/icons-vue'
import { historyApi, statsApi } from '@/api/v2'
import HistoryStatsCards, { type StatsSummary } from '@/components/HistoryStatsCards.vue'
import HistoryFilterBar from '@/components/HistoryFilterBar.vue'
import HistoryBatchToolbar from '@/components/HistoryBatchToolbar.vue'
import HistoryCard, { type HistoryBatch } from '@/components/HistoryCard.vue'
import { type ApiResponse } from '@/utils/request'
import { getErrorMessage } from '@/utils/error'

// ── 类型定义(与后端 /api/v2/history、/api/v2/stats 响应结构对齐)──


/** /api/v2/stats 响应 data 结构(仅声明本页使用的字段) */
interface StatsData {
  total?: number
  successRate?: number
  monthlyTotal?: number
  tasks?: { total?: number; successRate?: number }
}

/** 批量删除接口的失败项 */
interface BatchDeleteFailed {
  batch_id: string
  reason: string
}


const router = useRouter()
const batches = ref<HistoryBatch[]>([])
const stats = ref<StatsSummary>({ total: 0, successRate: 0, monthlyTotal: 0 })
const loading = ref(false)

// Filters
const timeRange = ref('all')
const typeFilter = ref('all')
const platformFilter = ref('all')
const statusFilter = ref('all')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

// 多选 + 删除状态
const selection = ref<Set<string>>(new Set())   // 选中的批次 id
const selectMode = ref(false)              // 多选模式开关
const isDeleting = ref(false)

async function fetchHistory() {
  loading.value = true
  try {
    const params: {
      page: number
      pageSize: number
      timeRange?: string
      type?: string
      platform?: string
      status?: string
    } = { page: currentPage.value, pageSize: pageSize.value }
    if (timeRange.value !== 'all') params.timeRange = timeRange.value
    if (typeFilter.value !== 'all') params.type = typeFilter.value
    if (platformFilter.value !== 'all') params.platform = platformFilter.value
    if (statusFilter.value !== 'all') params.status = statusFilter.value
    const res = (await historyApi.getHistory(params)) as ApiResponse<{ items?: HistoryBatch[]; total?: number }>
    if (res.code === 200) {
      batches.value = res.data?.items || []
      total.value = res.data?.total || 0
    }
  } catch (e) {
    console.error('Failed to fetch history:', e)
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  try {
    const res = (await statsApi.getStats()) as ApiResponse<StatsData>
    if (res.code === 200 && res.data) {
      const d = res.data
      stats.value = {
        total: d.total ?? d.tasks?.total ?? 0,
        successRate: d.successRate ?? d.tasks?.successRate ?? 0,
        monthlyTotal: d.monthlyTotal ?? 0,
      }
    }
  } catch (e) {
    console.error('Failed to fetch stats:', e)
  }
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  if (selectMode.value) selection.value = new Set()
  fetchHistory()
}
const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  if (selectMode.value) selection.value = new Set()
  fetchHistory()
}
const handleFilterChange = () => {
  currentPage.value = 1
  if (selectMode.value) selection.value = new Set()
  fetchHistory()
}

function goDetail(batchId: string) {
  router.push(`/publish-history/${batchId}`)
}

// ===== 多选操作 =====
const isAllSelected = computed(() => {
  const cnt = batches.value.length
  return cnt > 0 && selection.value.size >= cnt
})
const isIndeterminate = computed(() => {
  return selection.value.size > 0 && selection.value.size < batches.value.length
})

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) {
    selection.value = new Set()
  }
}

function toggleSelectAll(checked: CheckboxValueType) {
  selection.value = checked ? new Set(batches.value.map((b) => b.id)) : new Set()
}

function toggleSelection(id: string, checked: boolean) {
  const next = new Set(selection.value)
  if (checked) next.add(id)
  else next.delete(id)
  selection.value = next
}

function onCardClick(id: string) {
  if (!selectMode.value) {
    goDetail(id)
    return
  }
  toggleSelection(id, !selection.value.has(id))
}

// ===== 单条删除 =====
async function confirmDelete(batch: HistoryBatch) {
  const title = batch.title || '无标题'
  try {
    await ElMessageBox.confirm(
      `确定删除发布记录「${title}」吗？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await historyApi.deleteBatch(batch.id)
    ElMessage.success('记录已删除')
    // 本地移除并修正总数
    batches.value = batches.value.filter((b) => b.id !== batch.id)
    total.value = Math.max(0, total.value - 1)
    // 当前页空了且不是第一页时回退一页
    if (batches.value.length === 0 && currentPage.value > 1) {
      currentPage.value -= 1
      fetchHistory()
    } else if (batches.value.length === 0) {
      // 第一页也没有数据,刷新统计
      fetchStats()
    }
  } catch {
    // 错误提示已由响应拦截器处理
  }
}

// ===== 批量删除 =====
async function onBatchDelete() {
  const count = selection.value.size
  if (count === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${count} 条发布记录？此操作不可恢复。`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  const ids = [...selection.value]
  isDeleting.value = true
  try {
    const resp = (await historyApi.batchDelete(ids)) as {
      deleted?: string[]
      failed?: BatchDeleteFailed[]
    }
    const { deleted = [], failed = [] } = resp || {}
    if (deleted.length) {
      ElMessage.success(`已删除 ${deleted.length} 条记录`)
      batches.value = batches.value.filter((b) => !deleted.includes(b.id))
      total.value = Math.max(0, total.value - deleted.length)
    }
    if (failed.length) {
      ElMessage.warning(`${failed.length} 条删除失败：${failed.map((f) => f.reason).join('; ')}`)
    }
    selection.value = new Set()
    // 当前页删空了,回退或刷新
    if (batches.value.length === 0 && currentPage.value > 1) {
      currentPage.value -= 1
      fetchHistory()
    } else if (batches.value.length === 0) {
      fetchStats()
    } else if (deleted.length) {
      fetchStats()
    }
  } catch (e) {
    ElMessage.error(`批量删除失败：${getErrorMessage(e)}`)
  } finally {
    isDeleting.value = false
  }
}

onMounted(() => { fetchHistory(); fetchStats() })
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.publish-history-page {
  padding: 0 28px;

  // Page title area
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

  // ========== Filter Toolbar ==========

  // ========== Batch Operations Toolbar ==========

  .toolbar-select-all {
    :deep(.el-checkbox__label) {
      color: $text-secondary;
      font-size: 13px;
    }
  }

  .toolbar-spacer {
    flex: 1;
  }

  .selected-info {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    background: linear-gradient(135deg, rgba($brand-start, 0.18), rgba($brand-end, 0.12));
    border: 1px solid rgba($brand-start, 0.25);
    color: lighten($brand-start, 12%);
    font-size: 13px;
    border-radius: 999px;
    font-variant-numeric: tabular-nums;

    .selected-icon {
      font-size: 12px;
      color: $brand-start;
    }

    strong {
      color: $text-primary;
      font-weight: 600;
    }
  }

  .toolbar-exit {
    --el-button-bg-color: rgba($overlay-rgb, 0.03);
    --el-button-border-color: rgba($overlay-rgb, 0.12);
    --el-button-text-color: $text-secondary;
    --el-button-hover-bg-color: rgba($accent-rose, 0.12);
    --el-button-hover-border-color: rgba($accent-rose, 0.4);
    --el-button-hover-text-color: lighten($accent-rose, 8%);
  }

  // ========== Cards Grid ==========
  .cards-grid {
    margin-top: 24px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
  }


  // 单条删除按钮(右上角,hover 显示)
  .card-delete-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 3;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(8px);
    border: none;
    color: rgba($overlay-rgb, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    opacity: 0;
    transition: all 0.2s;
    font-size: 14px;

    &:hover {
      background: rgba($danger-color, 0.9);
      color: #fff;
    }

    .batch-card:hover & {
      opacity: 1;
    }
  }

  // 多选模式下的选择圆圈
  .card-selector {
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 3;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(8px);
    border: 2px solid rgba($overlay-rgb, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.25s cubic-bezier(.22,.61,.36,1);
    cursor: pointer;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);

    .selector-icon {
      font-size: 16px;
      font-weight: 900;
      color: white;
      opacity: 0;
      transform: scale(0) rotate(-90deg);
      transition: all 0.25s cubic-bezier(.22,.61,.36,1);
    }

    // 选中状态:以选择圆圈自身的 .is-checked 类为钩子(双保险)
    // (同时也兼容父级 .batch-card.is-selected 钩子)
    &.is-checked,
    .batch-card.is-selected & {
      background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
      border-color: rgba($overlay-rgb, 0.95);
      box-shadow:
        0 0 0 3px rgba($brand-start, 0.35),
        0 4px 16px rgba($brand-start, 0.55);
      transform: scale(1.1);

      .selector-icon {
        opacity: 1;
        transform: scale(1) rotate(0deg);
      }
    }

    &:hover {
      border-color: rgba($overlay-rgb, 0.95);
      transform: scale(1.05);
    }
  }

  .card-cover {
    width: 100%;
    aspect-ratio: 16/9;
    background: $bg-surface;
    overflow: hidden;
    position: relative;
    flex-shrink: 0;

    img { width: 100%; height: 100%; object-fit: cover; }

    .cover-placeholder {
      position: absolute; inset: 0;
      display: flex; align-items: center; justify-content: center;
      color: $text-muted;
    }
  }

  .card-body {
    padding: 12px 16px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .card-title {
    font-size: 14px;
    font-weight: 600;
    color: $text-primary;
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .card-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    color: $text-muted;
    flex-wrap: wrap;
  }

  .meta-time {
    font-variant-numeric: tabular-nums;
  }

  .status-tag {
    padding: 1px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;

    &.status-success, &.status-partial {
      background: rgba($accent-green, 0.15); color: #67c23a;
    }
    &.status-failed {
      background: rgba($danger-color, 0.15); color: #f56c6c;
    }
    &.status-running {
      background: rgba($info-color, 0.15); color: #409eff;
    }
    &.status-pending, &.status-cancelled {
      background: rgba(0, 0, 0, 0.06); color: $text-muted;
    }
  }

  .card-stats {
    margin-top: 4px;
  }

  // Empty state
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;

    .empty-icon {
      font-size: 40px;
      color: $text-muted;
      margin-bottom: 12px;
    }

    p {
      font-size: 14px;
      color: $text-muted;
      margin: 0;
    }
  }

  // ========== Pagination ==========
  .pagination-wrapper {
    display: flex;
    justify-content: flex-end;
    margin-top: 20px;
    padding: 16px 20px;
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;

    :deep(.el-pagination) {
      --el-pagination-bg-color: transparent;
      --el-pagination-text-color: #{$text-secondary};
      --el-pagination-button-bg-color: rgba($overlay-rgb, 0.06);
      --el-pagination-hover-color: #{$brand-start};

      .btn-prev,
      .btn-next {
        background: rgba($overlay-rgb, 0.06);
        border: 1px solid $border;
        border-radius: $radius-sm;
        color: $text-secondary;

        &:hover {
          border-color: $border-active;
          color: $brand-start;
        }
      }

      .el-pager li {
        background: rgba($overlay-rgb, 0.04);
        border: 1px solid $border;
        border-radius: $radius-sm;
        color: $text-secondary;
        margin: 0 2px;

        &:hover {
          border-color: $border-active;
          color: $brand-start;
        }

        &.is-active {
          background: $gradient-brand;
          border-color: transparent;
          color: #fff;
        }
      }

      .el-pagination__total {
        color: $text-muted;
      }

      .el-pagination__sizes {
        .el-input__wrapper {
          background: rgba($overlay-rgb, 0.04);
          border: 1px solid $border;
          border-radius: $radius-sm;
          box-shadow: none;

          &:hover {
            border-color: $border-active;
          }
        }

        .el-input__inner {
          color: $text-secondary;
        }
      }
    }
  }
}
</style>
