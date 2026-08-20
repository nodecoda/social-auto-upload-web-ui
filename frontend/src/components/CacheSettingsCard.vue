<template>
  <div class="settings-card">
    <h3 class="card-title">
      <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
      缓存管理
    </h3>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">清理抽帧缓存</span>
        <span class="setting-desc">清除 data/frames/ 目录下所有已提取的视频帧画面，释放磁盘空间</span>
      </div>
      <div class="setting-control">
        <span v-if="cacheInfo.frames.count > 0" class="cache-size">{{ cacheInfo.frames.count }} 个文件 · {{ formatSize(cacheInfo.frames.size) }}</span>
        <span v-else class="cache-size empty">无缓存</span>
        <button class="cache-btn" :disabled="clearing || cacheInfo.frames.count === 0" @click="emit('clear', 'frames')">
          {{ clearing ? '清理中...' : '清理缓存' }}
        </button>
      </div>
    </div>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">清理日志文件</span>
        <span class="setting-desc">清除 7 天前的日志文件，保留最近一周的日志</span>
      </div>
      <div class="setting-control">
        <span v-if="cacheInfo.logs.oldCount > 0" class="cache-size">{{ cacheInfo.logs.oldCount }} 个过期文件 · {{ formatSize(cacheInfo.logs.size) }}</span>
        <span v-else class="cache-size empty">无过期日志</span>
        <button class="cache-btn" :disabled="clearing || cacheInfo.logs.oldCount === 0" @click="emit('clear', 'logs')">
          {{ clearing ? '清理中...' : '清理日志' }}
        </button>
      </div>
    </div>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">S3 视频缓存</span>
        <span class="setting-desc">清除 data/s3_video_cache/ 目录下从 S3 下载的本地视频副本</span>
      </div>
      <div class="setting-control">
        <span v-if="cacheInfo.s3_videos.count > 0" class="cache-size">{{ cacheInfo.s3_videos.count }} 个文件 · {{ formatSize(cacheInfo.s3_videos.size) }}</span>
        <span v-else class="cache-size empty">无缓存</span>
        <button class="cache-btn" :disabled="clearing || cacheInfo.s3_videos.count === 0" @click="emit('clear', 's3_videos')">
          {{ clearing ? '清理中...' : '清理缓存' }}
        </button>
      </div>
    </div>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">清理封面缓存</span>
        <span class="setting-desc">清除 data/covers/ 目录下视频发布裁剪生成的封面文件</span>
      </div>
      <div class="setting-control">
        <span v-if="cacheInfo.covers.count > 0" class="cache-size">{{ cacheInfo.covers.count }} 个文件 · {{ formatSize(cacheInfo.covers.size) }}</span>
        <span v-else class="cache-size empty">无缓存</span>
        <button class="cache-btn" :disabled="clearing || cacheInfo.covers.count === 0" @click="emit('clear', 'covers')">
          {{ clearing ? '清理中...' : '清理缓存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 缓存信息条目
export interface CacheEntry {
  count: number
  size: number
}

// 日志缓存条目(额外含过期文件数)
export interface LogsCacheEntry extends CacheEntry {
  oldCount: number
}

// 缓存管理面板状态
export interface CacheInfoState {
  frames: CacheEntry
  logs: LogsCacheEntry
  s3_videos: CacheEntry
  covers: CacheEntry
}

// 可清理的缓存目标
export type ClearCacheTarget = 'frames' | 'logs' | 's3_videos' | 'covers'

const props = defineProps<{
  cacheInfo: CacheInfoState
  clearing: boolean
}>()

const emit = defineEmits<{
  (e: 'clear', target: ClearCacheTarget): void
}>()

const formatSize = (bytes: number): string => {
  if (!bytes) return '0B'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

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

    .cache-size {
      font-size: 12px;
      color: $text-muted;
      font-family: 'Fira Code', monospace;
      white-space: nowrap;

      &.empty {
        opacity: 0.5;
      }
    }

    .cache-btn {
      padding: 8px 20px;
      border: 1px solid rgba($danger-color, 0.3);
      border-radius: $radius-base;
      background: rgba($danger-color, 0.06);
      color: $danger-color;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: $transition-base;
      font-family: inherit;
      outline: none;

      &:hover:not(:disabled) {
        background: rgba($danger-color, 0.12);
        border-color: rgba($danger-color, 0.5);
      }

      &:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
    }
  }
}
</style>
