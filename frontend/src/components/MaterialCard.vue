<template>
  <div
    class="msd-card"
    :class="{ selected }"
    @click="emit('select')"
  >
    <!-- Preview -->
    <div class="msd-card-preview">
      <img
        v-if="mat.file_type === 'image'"
        :src="getThumbUrl(mat)"
        :alt="mat.original_filename"
        loading="lazy"
        @error="onImageError"
      />
      <template v-else>
        <!-- 播放模式：内嵌视频 -->
        <video
          v-if="playing"
          :src="getMaterialFullUrl(mat)"
          class="msd-card-video-el"
          autoplay
          controls
          muted
          playsinline
          preload="metadata"
          @click.stop
          @ended="emit('video-ended')"
        />
        <!-- 关闭按钮（叠加在视频左上） -->
        <button
          v-if="playing"
          class="msd-card-video-close"
          aria-label="关闭预览"
          @click.stop="emit('toggle-play')"
        >
          <el-icon :size="14"><Close /></el-icon>
        </button>
        <!-- 缩略图模式 -->
        <template v-else>
          <img
            v-if="mat.thumbnail_url"
            :src="getThumbUrl(mat)"
            :alt="mat.original_filename"
            loading="lazy"
            class="msd-card-video-thumb"
            @error="onImageError"
          />
          <div v-else class="msd-card-video-fallback">
            <el-icon :size="32"><VideoPlay /></el-icon>
          </div>
          <!-- 居中播放按钮 -->
          <button
            class="msd-card-play-btn"
            :aria-label="`预览 ${mat.original_filename}`"
            @click.stop="emit('toggle-play')"
          >
            <el-icon :size="20"><VideoPlay /></el-icon>
          </button>
          <!-- 视频类型徽章 -->
          <div class="msd-card-video-badge">
            <el-icon :size="11"><VideoPlay /></el-icon>
            <span>视频</span>
          </div>
        </template>
      </template>

      <!-- Selected check -->
      <div v-if="selected" class="msd-card-check">
        <el-icon :size="14"><Check /></el-icon>
      </div>

      <!-- 存储方式标识 -->
      <span class="msd-card-storage-badge" :class="{ s3: mat.storage_type === 's3' }">
        <el-icon :size="10"><component :is="mat.storage_type === 's3' ? 'Upload' : 'Monitor'" /></el-icon>
        {{ mat.storage_type === 's3' ? 'S3' : '本地' }}
      </span>

      <!-- Hover overlay：仅显示日期（大小已常驻在 caption） -->
      <div class="msd-card-hover-info">
        <span class="msd-card-date">{{ formatDate(mat.upload_time) }}</span>
      </div>
    </div>
    <!-- Caption -->
    <div class="msd-card-caption">
      <span class="msd-card-name" :title="mat.original_filename">
        {{ mat.original_filename }}
      </span>
      <span class="msd-card-meta">
        <span v-if="mat.file_size">{{ formatSize(mat.file_size) }}</span>
        <span v-if="mat.duration && mat.file_type === 'video'" class="msd-card-meta-dur">
          {{ Math.round(mat.duration) }}s
        </span>
        <span v-if="mat.upload_time" class="msd-card-meta-date">{{ formatDate(mat.upload_time) }}</span>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { VideoPlay, Check, Close, Upload, Monitor } from '@element-plus/icons-vue'
import { getFileUrl } from '@/utils/storage'

interface MaterialCardItem {
  id: number | string
  original_filename: string
  file_type: 'image' | 'video' | string
  thumbnail_url?: string
  stored_path: string
  storage_type?: string
  file_size?: number
  duration?: number
  upload_time?: string
  [key: string]: unknown
}

const props = withDefaults(defineProps<{
  mat: MaterialCardItem
  selected?: boolean
  playing?: boolean
}>(), {
  selected: false,
  playing: false,
})

const emit = defineEmits<{
  (e: 'select'): void
  (e: 'toggle-play'): void
  (e: 'video-ended'): void
}>()

const placeholderSvg =
  'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMDAiIGhlaWdodD0iMjAwIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iIzFhMWQyNCIvPjx0ZXh0IHg9IjEwMCIgeT0iMTA1IiBmb250LWZhbWlseT0ic2Fucy1zZXJpZiIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzY2NiIgdGV4dC1hbmNob3I9Im1pZGRsZSI+TG9hZGluZyBmYWlsZWQ8L3RleHQ+PC9zdmc+'

function getThumbUrl(mat: MaterialCardItem) {
  if (mat.thumbnail_url) return mat.thumbnail_url
  return getFileUrl(mat.stored_path)
}

function getMaterialFullUrl(mat: MaterialCardItem) {
  return getFileUrl(mat.stored_path)
}

function onImageError(e: Event) {
  ;(e.target as HTMLImageElement).src = placeholderSvg
}

function formatDate(iso: string | undefined) {
  if (!iso) return ''
  const d = new Date(iso.replace(' ', 'T') + (iso.endsWith('Z') ? '' : 'Z'))
  if (isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatSize(bytes: number) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;
$brand-1: #5b8cff;
$brand-2: #8b5cff;
$text-1: $text-primary;
$text-2: $text-secondary;
$text-3: $text-muted;
$border: rgba($overlay-rgb, 0.08);
$bg-card: rgba($overlay-rgb, 0.03);
$bg-card-hover: rgba($overlay-rgb, 0.05);

.msd-card {
  position: relative;
  border-radius: 10px;
  background: $bg-card;
  border: 1px solid $border;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    border-color: rgba($brand-1, 0.4);
    background: $bg-card-hover;
    transform: translateY(-2px);
    box-shadow:
      0 8px 20px rgba(0, 0, 0, 0.3),
      0 0 0 1px rgba($brand-1, 0.1);

    .msd-card-preview img { transform: scale(1.05); }
    .msd-card-hover-info { opacity: 1; }
  }

  &.selected {
    border-color: $brand-1;
    background: rgba($brand-1, 0.06);
    box-shadow:
      0 0 0 2px rgba($brand-1, 0.4),
      0 8px 24px rgba(0, 0, 0, 0.35);

    .msd-card-name { color: $brand-1; }
  }
}

.msd-card-preview {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba($overlay-rgb, 0.02), rgba($overlay-rgb, 0.06)),
    repeating-linear-gradient(45deg, transparent, transparent 8px, rgba($overlay-rgb, 0.01) 8px, rgba($overlay-rgb, 0.01) 16px);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 0.35s ease;
  }
}

.msd-card-video-thumb {
  // 视频缩略图保持 cover
}

.msd-card-video-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at center, rgba($brand-1, 0.1), transparent 70%),
    $bg-base;
  color: $text-2;
}

.msd-card-video-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(8px);
  border-radius: 4px;
  color: #fff;
  font-size: 10px;
  font-weight: 500;
}

.msd-card-storage-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid rgba($overlay-rgb, 0.15);
  border-radius: 4px;
  color: #d1d5db;
  font-size: 11px;
  font-weight: 600;
  z-index: 2;
  letter-spacing: 0.3px;

  &.s3 {
    color: #fff;
    background: rgba($info-color, 0.7);
    border-color: rgba($info-color, 0.5);
  }
}

// 居中播放按钮 — 默认半透明，hover 缩放高亮
.msd-card-play-btn {
  position: absolute;
  inset: 0;
  margin: auto;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(8px);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 0 0 3px; // 视觉居中（图标三角形）
  opacity: 0.85;
  transition: all 0.2s ease;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.4);

  &:hover {
    opacity: 1;
    transform: scale(1.08);
    background: linear-gradient(135deg, $brand-1, $brand-2);
    box-shadow: 0 4px 18px rgba($brand-1, 0.5);
  }
}

.msd-card-video-el {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
  display: block;
}

.msd-card-video-close {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  z-index: 2;

  &:hover {
    background: rgba($danger-color, 0.85);
    transform: scale(1.08);
  }
}

.msd-card-check {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, $brand-1, $brand-2);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    0 2px 8px rgba($brand-1, 0.5),
    inset 0 1px 0 rgba($overlay-rgb, 0.2);
  animation: msd-check-pop 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes msd-check-pop {
  0% { transform: scale(0); }
  100% { transform: scale(1); }
}

.msd-card-hover-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 6px 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(180deg, transparent, rgba(0, 0, 0, 0.75));
  color: #fff;
  font-size: 10px;
  opacity: 0;
  transition: opacity 0.2s ease;
  pointer-events: none;
}

.msd-card-caption {
  padding: 6px 8px 8px;
}

.msd-card-name {
  display: block;
  font-size: 12px;
  color: $text-1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  transition: color 0.15s ease;
}

// 常驻的元信息行：大小 / 时长 / 日期
.msd-card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  font-size: 10px;
  color: $text-3;
  font-variant-numeric: tabular-nums;
  overflow: hidden;
  white-space: nowrap;

  .msd-card-meta-dur { color: $brand-1; }
  .msd-card-meta-date {
    margin-left: auto;
    opacity: 0.8;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

// ===== Empty =====
</style>
