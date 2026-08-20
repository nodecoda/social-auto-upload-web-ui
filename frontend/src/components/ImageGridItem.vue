<template>
  <div class="image-item" :data-index="index">
    <!-- Image preview -->
    <div class="image-preview">
      <img :src="image.url" :alt="image.name" @error="onImageError" />
      <!-- Uploading overlay -->
      <div v-if="image.uploading" class="uploading-overlay">
        <el-progress
          type="circle"
          :percentage="image.progress || 0"
          :width="48"
          :stroke-width="4"
          color="#8b5cf6"
        />
      </div>
      <!-- Hover overlay -->
      <div v-else class="image-overlay">
        <button class="overlay-btn" @click.stop="emit('re-upload', index)" title="重新上传">
          <el-icon :size="16"><RefreshRight /></el-icon>
        </button>
        <button class="overlay-btn" @click.stop="emit('open-material-library', index)" title="从素材库选择">
          <el-icon :size="16"><FolderOpened /></el-icon>
        </button>
        <button class="overlay-btn danger" @click.stop="emit('remove', index)" title="删除">
          <el-icon :size="16"><Delete /></el-icon>
        </button>
      </div>
      <!-- Sort handle -->
      <div class="sort-handle" title="拖拽排序">
        <el-icon :size="14"><Rank /></el-icon>
      </div>
      <!-- Index badge -->
      <span class="index-badge">{{ index + 1 }}</span>
    </div>
    <div class="image-name" :title="image.name">{{ image.name }}</div>
  </div>
</template>

<script setup lang="ts">
import { RefreshRight, FolderOpened, Delete, Rank } from '@element-plus/icons-vue'

export interface UploadImageItem {
  id: number | string
  name: string
  url: string
  stored_path?: string
  size?: number
  type?: string
  uploading: boolean
  progress: number
}

const props = defineProps<{
  image: UploadImageItem
  index: number
}>()

const emit = defineEmits<{
  (e: 're-upload', index: number): void
  (e: 'open-material-library', index: number): void
  (e: 'remove', index: number): void
}>()

function onImageError(e: Event) {
  ;(e.target as HTMLImageElement).src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmlsbD0iIzIyMiIvPjx0ZXh0IHg9IjUwIiB5PSI1MCIgZm9udC1mYW1pbHk9IkFyaWFsIiBmb250LXNpemU9IjEyIiBmaWxsPSIjNjY2IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+5Zu+54mH5Yqg6L295aSx6LSlPC90ZXh0Pjwvc3ZnPg=='
}
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.image-item {
  position: relative;
  cursor: grab;

  &:active {
    cursor: grabbing;
  }
}

.image-preview {
  position: relative;
  aspect-ratio: 3 / 4;
  border-radius: $radius-sm;
  overflow: hidden;
  background: rgba($bg-base-rgb, 0.6);
  border: 2px solid transparent;
  transition: all 0.3s ease;

  &:hover {
    border-color: rgba($brand-start, 0.3);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);

    .image-overlay {
      opacity: 1;
    }

    .sort-handle {
      opacity: 1;
    }
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.image-name {
  margin-top: 6px;
  font-size: 11px;
  color: $text-secondary;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0 2px;
}

.uploading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  opacity: 0;
  transition: opacity $transition-fast;
}

.overlay-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba($overlay-rgb, 0.2);
  background: rgba($overlay-rgb, 0.1);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: $transition-fast;
  backdrop-filter: blur(4px);

  &:hover {
    background: rgba($overlay-rgb, 0.2);
    border-color: rgba($overlay-rgb, 0.4);
    transform: scale(1.1);
  }

  &.danger:hover {
    background: rgba($danger-color, 0.6);
    border-color: rgba($danger-color, 0.8);
  }
}

.sort-handle {
  position: absolute;
  top: 4px;
  left: 4px;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.6);
  color: rgba($overlay-rgb, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
  opacity: 0;
  transition: opacity $transition-fast;
  backdrop-filter: blur(4px);

  &:hover {
    background: rgba(0, 0, 0, 0.8);
  }

  &:active {
    cursor: grabbing;
  }
}

.index-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.6);
  color: rgba($overlay-rgb, 0.9);
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}
</style>
