<template>
  <section class="content-snapshot" :class="{ 'content-snapshot--failed': item.status === 'failed' }">
    <!-- 失败错误横幅：仅失败时显示 -->
    <div v-if="item.status === 'failed'" class="error-banner">
      <el-icon :size="18"><CircleCloseFilled /></el-icon>
      <div class="error-banner-body">
        <strong>发布失败</strong>
        <span>{{ item.error_message || '未知错误' }}</span>
      </div>
    </div>
    <!-- 完整内容快照：成功 + 失败都显示 -->
    <div class="snapshot-body-row">
      <div class="snapshot-cover">
        <img v-if="getCoverUrl(item)" :src="getCoverUrl(item)" :alt="fallbackTitle" />
        <div v-else class="cover-placeholder">
          <el-icon :size="40"><Picture /></el-icon>
        </div>
      </div>
      <div class="snapshot-body">
        <h3 class="snapshot-title">{{ getCfgField(item, 'title') || fallbackTitle || '无标题' }}</h3>
        <p class="snapshot-desc">{{ getCfgField(item, 'description') || fallbackDescription || '无描述' }}</p>
        <div v-if="getCfgField<string[]>(item, 'tags')?.length" class="snapshot-tags">
          <el-tag v-for="t in getCfgField<string[]>(item, 'tags')" :key="t" size="small" effect="plain">#{{ t }}</el-tag>
        </div>
        <div v-if="getCfgField(item, 'creationDeclaration')" class="snapshot-meta">
          <span class="meta-label">作品声明</span>
          <span>{{ getCfgField(item, 'creationDeclaration') }}</span>
        </div>
        <div v-if="getCfgField(item, 'scheduleTime')" class="snapshot-meta">
          <span class="meta-label">定时发布时间</span>
          <span>{{ getCfgField(item, 'scheduleTime') }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { CircleCloseFilled, Picture } from '@element-plus/icons-vue'

export interface BatchItem {
  account_id: number | string
  status: string
  created_at?: string
  duration?: number
  publish_url?: string
  error_message?: string
  account_configs?: Record<string, unknown>
}

const props = defineProps<{
  item: BatchItem
  fallbackTitle?: string
  fallbackDescription?: string
  fallbackCoverUrl?: string
}>()

function getCfgField<T = string | string[]>(item: BatchItem, field: string): T | undefined {
  return item.account_configs?.[field] as T | undefined
}

function getCoverUrl(item: BatchItem): string {
  if (!item) return ''
  const cfg = item.account_configs || {}
  const coverLandscape = cfg.coverLandscape as { url?: string } | undefined
  const coverPortrait = cfg.coverPortrait as { url?: string } | undefined
  // 优先用 per-account cover 自带的 .url 字段（后端已构造为绝对 URL）
  if (coverLandscape?.url) return coverLandscape.url
  if (coverPortrait?.url) return coverPortrait.url
  // 兜底：batch 级 cover_url
  return props.fallbackCoverUrl || ''
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.content-snapshot {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 20px;
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  transition: $transition-base;

  &--failed {
    border-color: rgba($danger-color, 0.3);
    background: rgba($danger-color, 0.03);
  }
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: rgba($danger-color, 0.1);
  border: 1px solid rgba($danger-color, 0.3);
  border-radius: $radius-base;
  color: #f56c6c;

  .el-icon { flex-shrink: 0; }

  .error-banner-body {
    display: flex;
    flex-direction: column;
    gap: 2px;

    strong { font-size: 13px; font-weight: 600; }
    span { font-size: 12px; color: $text-secondary; word-break: break-all; }
  }
}

.snapshot-body-row {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.snapshot-cover {
  flex-shrink: 0;
  width: 160px;
  aspect-ratio: 16/9;
  background: $bg-surface;
  border-radius: 8px;
  overflow: hidden;
  position: relative;

  img { width: 100%; height: 100%; object-fit: cover; }
  .cover-placeholder {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    color: $text-muted;
  }
}

.snapshot-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.snapshot-title {
  font-size: 15px;
  font-weight: 600;
  color: $text-primary;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.snapshot-desc {
  font-size: 13px;
  color: $text-secondary;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.snapshot-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.snapshot-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: $text-secondary;
  .meta-label { color: $text-muted; }
}
</style>
