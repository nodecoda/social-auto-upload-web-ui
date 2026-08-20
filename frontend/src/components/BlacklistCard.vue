<template>
  <div class="settings-card">
    <div class="card-header">
      <h3 class="card-title">
        <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
        渠道黑名单
      </h3>
      <el-button type="primary" @click="emit('open')">
        <el-icon><Plus /></el-icon> 添加渠道
      </el-button>
    </div>
    <p class="card-desc">
      被加入黑名单的渠道，将无法在视频发布、图集发布、账号登录场景下被选择
    </p>

    <!-- 已拉黑渠道的小卡片网格 -->
    <div v-if="platforms.length" class="blacklist-grid">
      <div
        v-for="p in platforms"
        :key="p.key"
        class="blacklist-chip"
        :class="`platform-${p.cssClass}`"
      >
        <img v-if="p.logo" :src="p.logo" :alt="p.name" class="chip-logo" />
        <span class="chip-name">{{ p.name }}</span>
        <button class="chip-remove" type="button" @click="emit('remove', p.key)">
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </div>

    <!-- 空态 -->
    <div v-else class="blacklist-empty">
      <el-icon class="empty-icon"><Warning /></el-icon>
      <span>暂无黑名单渠道，点击右上角「添加渠道」开始</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Close, Warning } from '@element-plus/icons-vue'

interface BlacklistPlatform {
  key: string
  name: string
  logo?: string
  cssClass: string
}

defineProps<{
  platforms: BlacklistPlatform[]
}>()

const emit = defineEmits<{
  (e: 'open'): void
  (e: 'remove', key: string): void
}>()
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

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: $spacing-md;
    margin: 0 0 $spacing-sm 0;
    padding-bottom: $spacing-sm;
    border-bottom: 1px solid $border;

    .card-title {
      margin: 0;
      border-bottom: none;
      padding-bottom: 0;
    }
  }

  .card-desc {
    margin: 0 0 $spacing-md 0;
    font-size: 12px;
    color: $text-muted;
    line-height: 1.5;
  }

  .blacklist-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }

  .blacklist-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid $border;
    background: $bg-surface;
    position: relative;
    transition: all 0.2s;

    &:hover {
      border-color: var(--el-color-primary);
    }
  }

  .chip-logo {
    width: 18px;
    height: 18px;
    border-radius: 4px;
  }

  .chip-name {
    font-size: 13px;
    color: $text-primary;
  }

  .chip-remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    border: 0;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.4);
    color: white;
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.2s;
    padding: 0;
    margin-left: 2px;

    .blacklist-chip:hover & {
      opacity: 1;
    }

    &:hover {
      background: var(--el-color-danger);
    }
  }

  .blacklist-empty {
    display: flex;
    align-items: center;
    gap: 8px;
    color: $text-secondary;
    font-size: 13px;
    margin-top: 12px;
    padding: 16px;
    background: $bg-surface;
    border-radius: 8px;

    .empty-icon {
      font-size: 18px;
    }
  }
}
</style>
