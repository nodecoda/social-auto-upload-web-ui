<template>
  <div class="phone-panel">
    <div class="phone-panel-header">
      <span class="phone-panel-title">视频预览</span>
    </div>
    <div class="phone-preview-area">
      <div :class="['phone-mockup', modeTab]">
        <div class="phone-notch"></div>
        <div class="phone-screen">
          <template v-if="videoData">
            <video
              :src="videoData.url"
              controls
              preload="metadata"
              class="phone-video-player"
            ></video>
          </template>
          <template v-else>
            <div class="phone-empty" @click="$emit('upload')">
              <el-icon :size="28"><Upload /></el-icon>
              <span>上传视频</span>
            </div>
          </template>
        </div>
        <div class="phone-home-bar"></div>
      </div>
    </div>
    <div class="phone-panel-actions">
      <button class="cover-action-btn primary" @click="$emit('upload')">
        <el-icon :size="14"><Upload /></el-icon><span>本地上传</span>
      </button>
      <button class="cover-action-btn" @click="$emit('library')">
        <el-icon :size="14"><Picture /></el-icon><span>素材库</span>
      </button>
    </div>
    <div v-if="videoData" class="phone-panel-info">
      <span class="phone-info-name">{{ videoData.name }}</span>
      <button class="phone-info-remove" @click="$emit('remove')">
        <el-icon :size="12"><Delete /></el-icon>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { type PropType } from 'vue'
import { Upload, Picture, Delete } from '@element-plus/icons-vue'

interface VideoData {
  url: string
  name?: string
}

defineProps({
  // { url, name } | null
  videoData: { type: Object as PropType<VideoData | null>, default: null },
  // horizontal→landscape, 其余→portrait
  modeTab: { type: String, default: 'portrait' },
})

defineEmits(['upload', 'library', 'remove'])
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.phone-panel {
  width: 400px;
  flex-shrink: 0;
  background: $bg-base;
  border-left: 1px solid $border;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba($overlay-rgb, 0.08) transparent;
  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: rgba($overlay-rgb, 0.1); border-radius: 2px; }
}

.phone-panel-header {
  padding: 16px 16px 12px;
  border-bottom: 1px solid $border;
}

.phone-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
}

.phone-preview-area {
  display: flex;
  justify-content: center;
  padding: 16px 4px;
}

.phone-mockup {
  position: relative;
  background: #1a1a2e;
  border: 3px solid #2a2a40;
  border-radius: 28px;
  padding: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), inset 0 0 0 1px rgba($overlay-rgb, 0.05);
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: width 0.3s ease;

  width: 90%;
}

.phone-notch {
  width: 60px;
  height: 6px;
  background: #2a2a40;
  border-radius: 3px;
  margin-bottom: 6px;
}

.phone-screen {
  width: 100%;
  aspect-ratio: 9 / 16;
  background: $bg-base;
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.phone-video-player {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  outline: none;
}

.phone-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  color: $text-muted;
  font-size: 11px;
  cursor: pointer;
  transition: $transition-fast;

  &:hover {
    color: $brand-start;
    background: rgba($brand-start, 0.04);
  }
}

.phone-home-bar {
  width: 40px;
  height: 4px;
  background: rgba($overlay-rgb, 0.15);
  border-radius: 2px;
  margin-top: 6px;
}

.phone-panel-actions {
  display: flex;
  gap: 8px;
  padding: 0 16px 12px;
  .cover-action-btn { flex: 1; }
}

.phone-panel-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 16px;
  padding: 10px 12px;
  background: rgba($overlay-rgb, 0.03);
  border: 1px solid $border;
  border-radius: $radius-base;
}

.phone-info-name {
  font-size: 12px;
  color: $text-secondary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.phone-info-remove {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: $text-muted;
  cursor: pointer;
  transition: $transition-fast;
  &:hover {
    background: rgba($danger-color, 0.1);
    color: $danger-color;
  }
}

.cover-action-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border: 1px solid $border;
  border-radius: $radius-sm;
  background: rgba($overlay-rgb, 0.03);
  color: $text-secondary;
  font-size: 12px;
  cursor: pointer;
  transition: $transition-base;
  outline: none;
  font-family: inherit;
  line-height: 1;

  .el-icon {
    flex-shrink: 0;
    color: $text-muted;
    transition: $transition-base;
  }

  &:hover {
    border-color: rgba($brand-start, 0.35);
    background: linear-gradient(135deg, rgba($brand-start, 0.08), rgba($brand-end, 0.06));
    color: $text-primary;

    .el-icon {
      color: $brand-start;
    }
  }

  &:active {
    transform: scale(0.97);
  }

  &.primary {
    border-color: rgba($brand-start, 0.25);
    background: linear-gradient(135deg, rgba($brand-start, 0.1), rgba($brand-end, 0.08));
    color: $text-primary;

    .el-icon {
      color: $brand-start;
    }

    &:hover {
      border-color: rgba($brand-start, 0.45);
      background: linear-gradient(135deg, rgba($brand-start, 0.18), rgba($brand-end, 0.14));
    }
  }

  &.danger {
    &:hover {
      border-color: rgba($danger-color, 0.35);
      background: rgba($danger-color, 0.08);
      color: $danger-color;

      .el-icon {
        color: $danger-color;
      }
    }
  }
}
</style>
