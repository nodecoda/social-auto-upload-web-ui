<template>
  <div
    class="batch-card"
    :class="{
      'is-selected': selection.has(batch.id),
      'select-mode': selectMode,
    }"
    @click="emit('card-click', batch.id)"
  >
    <div
      v-if="selectMode"
      class="card-selector"
      :class="{ 'is-checked': selection.has(batch.id) }"
      @click.stop="emit('toggle-selection', batch.id, !selection.has(batch.id))"
    >
      <el-icon class="selector-icon"><Check /></el-icon>
    </div>
    <div class="card-cover">
      <img v-if="batch.cover_url" :src="batch.cover_url" :alt="batch.title" />
      <div v-else class="cover-placeholder">
        <el-icon :size="32"><Picture /></el-icon>
      </div>
    </div>
    <div class="card-body">
      <h3 class="card-title">{{ batch.title || '无标题' }}</h3>
      <ChannelSummary
        :channels="computeChannelsSummary(batch.items)"
        :overflow-key="batch.id"
      />
      <div class="card-meta">
        <span class="meta-time">{{ formatCardTime(batch.created_at) }}</span>
        <span class="status-tag" :class="`status-${batch.status}`">{{ statusLabel(batch.status) }}</span>
      </div>
      <div class="card-stats">
        <PublishStats compact />
      </div>
    </div>

    <!-- 单条删除按钮（非多选模式下显示） -->
    <button
      v-if="!selectMode"
      class="card-delete-btn"
      @click.stop="emit('delete', batch)"
    >
      <el-icon><Delete /></el-icon>
    </button>
  </div>
</template>

<script setup lang="ts">
import ChannelSummary from '@/components/ChannelSummary.vue'
import PublishStats from '@/components/PublishStats.vue'
import { Check, Picture, Delete } from '@element-plus/icons-vue'
import { platformList, getPlatformByKey } from '@/config/platforms'

// ── 类型定义(与后端 /api/v2/history 响应结构对齐)──

/** 发布明细(单个账号一条) */
export interface HistoryDetailItem {
  id: string
  account_name: string
  platform: string // 中文平台名(如 '抖音')
  status?: string
}

/** 发布批次(卡片) */
export interface HistoryBatch {
  id: string
  type?: string
  title: string
  description?: string
  cover_url?: string
  status: string
  created_at?: string
  items: HistoryDetailItem[]
}

/** computeChannelsSummary 返回的平台汇总(与 ChannelSummary 组件 props 结构一致) */
interface ChannelGroup {
  platform: string
  name: string
  count: number
  logo?: string
}

const props = defineProps<{
  batch: HistoryBatch
  selectMode: boolean
  selection: Set<string>
}>()

const emit = defineEmits<{
  (e: 'card-click', id: string): void
  (e: 'toggle-selection', id: string, checked: boolean): void
  (e: 'delete', batch: HistoryBatch): void
}>()

function computeChannelsSummary(items: HistoryDetailItem[]): ChannelGroup[] {
  const groups: Record<string, ChannelGroup> = {}
  for (const it of items || []) {
    const key = it.platform
    if (!groups[key]) {
      const cfg = getPlatformByKey(platformList.find(p => p.name === key)?.key ?? '')
      // 兜底用 undefined 替代原 null:二者均 falsy,模板 v-if="ch.logo" 行为一致,
      // 同时与 ChannelSummaryItem.logo?: string 类型兼容
      groups[key] = { platform: key, name: it.platform, count: 0, logo: cfg?.logo || undefined }
    }
    groups[key].count++
  }
  return Object.values(groups)
}

function statusLabel(status: string): string {
  return ({
    pending: '等待中',
    running: '发布中',
    success: '全部成功',
    partial: '部分失败',
    failed: '全部失败',
    cancelled: '已取消',
  }[status] || status)
}

function formatCardTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 86400) {
    if (diff < 60) return '刚刚'
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
    return `${Math.floor(diff / 3600)} 小时前`
  }
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
.batch-card {
  position: relative;
  border: 1px solid $border;
  border-radius: $radius-card;
  background: $bg-elevated;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;

  &:hover {
    border-color: rgba($brand-start, 0.5);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    transform: translateY(-1px);
  }

  &.select-mode {
    cursor: pointer;
  }

  &.is-selected {
    border-color: rgba($brand-start, 0.8);
    background: linear-gradient(135deg, rgba($brand-start, 0.15), rgba($brand-end, 0.08));
    box-shadow:
      0 0 0 2px $brand-start,
      0 8px 32px rgba($brand-start, 0.35);
    transform: translateY(-2px);

    // 多选模式下隐藏单条删除按钮,避免误触
    .card-delete-btn { display: none; }
  }
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

</style>
