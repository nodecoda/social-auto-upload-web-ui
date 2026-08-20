<template>
  <div class="qr-card" :style="{ '--accent': qr.accent }">
    <div class="qr-card-head">
      <div class="qr-icon" :style="{ background: qr.iconBg }">
        <component :is="qr.icon" />
      </div>
      <div class="qr-name">{{ qr.name }}</div>
      <div class="qr-tag">扫码支持</div>
    </div>
    <div class="qr-img-wrap" @click="emit('preview', qr)">
      <img :src="qr.img" :alt="qr.name">
      <div class="qr-img-mask">
        <span>👆 点击放大</span>
      </div>
    </div>
    <div class="qr-card-foot">
      <span class="emoji">{{ qr.emoji }}</span>
      <span>{{ qr.slogan }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

interface QrCodeItem {
  name: string
  img: string
  accent: string
  iconBg: string
  icon: Component
  emoji: string
  slogan: string
}

const props = defineProps<{
  qr: QrCodeItem
}>()

const emit = defineEmits<{
  (e: 'preview', qr: QrCodeItem): void
}>()
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
.qr-card {
  padding: 16px 18px 16px;
  border-radius: 16px;
  background: $bg-elevated;
  border: 1px solid $border;
  text-align: center;
  transition: all $transition-base;
  position: relative;
  overflow: hidden;

  // 顶部一道彩色高光
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--accent);
    opacity: 0.7;
  }

  &:hover {
    transform: translateY(-4px);
    border-color: var(--accent);
    box-shadow: 0 16px 32px rgba(0, 0, 0, 0.25), 0 0 0 4px rgba(255, 255, 255, 0.04);
  }
}

.qr-card-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 10px;
}

.qr-icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;

  :deep(svg) {
    width: 14px;
    height: 14px;
    color: #fff;
  }
}

.qr-name {
  font-size: 14px;
  font-weight: 700;
  color: $text-primary;
}

.qr-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(var(--accent), 0.15);
  color: var(--accent);
  font-weight: 600;
  letter-spacing: 0.5px;
}

.qr-img-wrap {
  width: 100%;
  max-width: 170px;
  aspect-ratio: 1;
  margin: 0 auto;
  border-radius: 10px;
  background: #fff;
  padding: 8px;
  position: relative;
  cursor: zoom-in;
  overflow: hidden;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 4px;
    transition: transform $transition-base;
  }

  .qr-img-mask {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    opacity: 0;
    transition: opacity $transition-base;
    border-radius: 10px;
  }

  &:hover .qr-img-mask { opacity: 1; }
  &:hover img { transform: scale(1.04); }
}

.qr-card-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 11.5px;
  color: $text-muted;

  .emoji { font-size: 13px; }
}
</style>
