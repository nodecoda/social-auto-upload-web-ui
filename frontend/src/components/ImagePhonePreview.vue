<template>
  <div class="phone-panel">
    <div class="phone-panel-header">
      <span class="phone-panel-title">图片预览</span>
      <button
        v-if="images.length > 0"
        class="cover-action-btn"
        @click="$emit('preview')"
      >
        <el-icon :size="14"><FullScreen /></el-icon><span>放大预览</span>
      </button>
    </div>

    <div class="phone-preview-area">
      <div class="phone-mockup">
        <div class="phone-notch"></div>
        <div class="phone-screen">
          <ImageCarousel
            v-if="images.length > 0"
            :images="images"
            @change="$emit('carousel-change', $event)"
          />
          <div v-else class="phone-empty" @click="$emit('upload')">
            <el-icon :size="28"><Upload /></el-icon>
            <span>上传图片</span>
          </div>
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

    <div v-if="images.length > 0" class="phone-panel-info">
      <span class="phone-info-name">{{ images[previewIndex]?.name || '未选择图片' }}</span>
      <span class="phone-info-count">{{ previewIndex + 1 }}/{{ images.length }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { FullScreen, Upload, Picture } from '@element-plus/icons-vue'
import ImageCarousel from '@/components/ImageCarousel.vue'

interface PhoneImageItem {
  url: string
  name?: string
  id?: number | string
}

withDefaults(defineProps<{
  images?: PhoneImageItem[]
  previewIndex?: number
}>(), {
  images: () => [],
  previewIndex: 0,
})

defineEmits<{
  (e: 'upload'): void
  (e: 'library'): void
  (e: 'preview'): void
  (e: 'carousel-change', index: number): void
}>()
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.phone-panel {
  width: 380px;
  flex-shrink: 0;
  background: linear-gradient(180deg, $bg-elevated 0%, $bg-base 100%);
  border-left: 1px solid rgba($overlay-rgb, 0.06);
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba($brand-start, 0.1) transparent;
  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: rgba($brand-start, 0.1); border-radius: 2px; }
}

.phone-panel-header {
  padding: 16px 20px 12px;
  border-bottom: 1px solid rgba($overlay-rgb, 0.06);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.phone-panel-title {
  font-size: 15px;
  font-weight: 700;
  color: $popper-text;
}

.phone-preview-area {
  display: flex;
  justify-content: center;
  padding: 20px 4px;
}

.phone-mockup {
  position: relative;
  background: linear-gradient(145deg, #1e1e3a, #14142a);
  border: 2px solid rgba($brand-start, 0.12);
  border-radius: 36px;
  padding: 10px;
  box-shadow:
    0 16px 48px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba($brand-start, 0.06),
    0 0 60px rgba($brand-start, 0.06);
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: all 0.3s ease;
  width: 88%;

  &:hover {
    box-shadow:
      0 20px 56px rgba(0, 0, 0, 0.55),
      0 0 0 1px rgba($brand-start, 0.1),
      0 0 80px rgba($brand-start, 0.1);
    transform: translateY(-2px);
  }
}

.phone-notch {
  width: 80px;
  height: 6px;
  background: rgba($overlay-rgb, 0.08);
  border-radius: 3px;
  margin-bottom: 8px;
}

.phone-screen {
  width: 100%;
  aspect-ratio: 9 / 16;
  background: $bg-base;
  border-radius: 20px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.phone-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  height: 100%;
  color: $text-muted;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 500;

  &:hover {
    color: $brand-start;
    background: rgba($brand-start, 0.03);
    .el-icon { transform: scale(1.1); }
  }

  .el-icon { transition: transform 0.2s ease; }
}

.phone-home-bar {
  width: 48px;
  height: 4px;
  background: linear-gradient(90deg, #8b5cf6, #3b82f6);
  border-radius: 2px;
  margin-top: 8px;
  opacity: 0.5;
}

.phone-panel-actions {
  display: flex;
  gap: 10px;
  padding: 4px 20px 16px;
  .cover-action-btn { flex: 1; }
}

.phone-panel-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 20px;
  padding: 10px 14px;
  background: rgba($overlay-rgb, 0.025);
  border: 1px solid rgba($overlay-rgb, 0.06);
  border-radius: 10px;
}

.phone-info-name {
  font-size: 12px;
  color: $text-secondary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.phone-info-count {
  font-size: 11px;
  color: #a78bfa;
  font-weight: 600;
  flex-shrink: 0;
  margin-left: 8px;
}

.cover-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid rgba($overlay-rgb, 0.08);
  border-radius: 10px;
  background: rgba($overlay-rgb, 0.025);
  color: $text-secondary;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;
  font-family: inherit;
  line-height: 1;

  .el-icon { flex-shrink: 0; color: $text-muted; transition: all 0.2s ease; }

  &:hover {
    border-color: rgba($brand-start, 0.25);
    background: rgba($brand-start, 0.06);
    color: $text-primary;
    .el-icon { color: $brand-start; }
  }

  &:active { transform: scale(0.97); }

  &.primary {
    border-color: rgba($brand-start, 0.2);
    background: rgba($brand-start, 0.08);
    color: #c4b5fd;
    .el-icon { color: $brand-start; }

    &:hover {
      border-color: rgba($brand-start, 0.35);
      background: rgba($brand-start, 0.14);
    }
  }
}
</style>
