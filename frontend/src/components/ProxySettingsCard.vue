<template>
  <div class="settings-card">
    <h3 class="card-title">
      <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
      网络代理
    </h3>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">HTTP 代理地址</span>
        <span class="setting-desc">用于 YouTube、TikTok 等海外平台的浏览器连接，国内平台无需代理</span>
      </div>
      <div class="setting-control">
        <el-input
          v-model="proxyUrl"
          placeholder="http://127.0.0.1:7897"
          style="width: 300px"
          clearable
        />
      </div>
    </div>
    <div class="proxy-platforms">
      <span class="proxy-tag" v-for="p in overseasPlatforms" :key="p.key">
        <img :src="p.logo" :alt="p.name" class="proxy-tag-logo" />
        {{ p.name }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface PlatformMeta {
  key: string
  name: string
  logo?: string
}

const props = defineProps<{
  proxyUrl: string
  overseasPlatforms: PlatformMeta[]
}>()

const emit = defineEmits<{
  (e: 'update:proxyUrl', v: string): void
}>()

const proxyUrl = computed({
  get: () => props.proxyUrl,
  set: (v: string) => emit('update:proxyUrl', v),
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

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
  }

  .proxy-platforms {
    display: flex;
    gap: $spacing-sm;
    margin-top: $spacing-sm;
    padding-left: 4px;

    .proxy-tag {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 500;
      background: $bg-surface;
      border: 1px solid $border;
      color: $text-secondary;

      .proxy-tag-logo {
        width: 16px;
        height: 16px;
        border-radius: 3px;
      }
    }
  }
}
</style>
