<template>
  <section class="account-header">
    <div class="avatar" :style="{ borderColor: platformConfig?.color || '#666' }">
      {{ account?.name?.charAt(0) || '?' }}
    </div>
    <div class="header-text">
      <div class="line-1">
        <span class="account-name">{{ account?.name || '已删除账号' }}</span>
        <span v-if="platformConfig" class="platform-badge" :style="{ background: platformConfig.color + '20', color: platformConfig.color }">
          {{ platformConfig.name }}
        </span>
        <span class="status-tag" :class="`status-${item.status}`">{{ statusLabel(item.status) }}</span>
      </div>
      <div class="line-2">
        <span class="meta-time">{{ formatTime(item.created_at) }}</span>
        <span v-if="item.duration" class="meta-time">耗时 {{ formatDuration(item.duration) }}</span>
      </div>
    </div>
    <a
      v-if="item.status === 'success' && item.publish_url"
      :href="item.publish_url"
      target="_blank"
      rel="noopener noreferrer"
      class="view-link"
    >
      查看发布作品 →
    </a>
  </section>
</template>

<script setup lang="ts">
import { type BatchItem } from '@/components/PublishSnapshot.vue'
import { statusLabel, formatTime, formatDuration } from '@/components/publishHistoryShared'

interface PlatformAccountMeta {
  name: string
}
interface PlatformConfigMeta {
  color: string
  name: string
}

defineProps<{
  item: BatchItem
  account: PlatformAccountMeta | null
  platformConfig: PlatformConfigMeta | null
}>()
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

// 1. 账号信息头：圆角 12px + 1px 边框 + 48px 头像，header 内部 16px gap
.account-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  transition: border-color $transition-base;
  &:hover { border-color: $border-active; }

  .avatar {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: rgba($brand-start, 0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    color: #c4b5fd;
    font-weight: 700;
    border: 2px solid transparent;
    flex-shrink: 0;
  }

  .header-text {
    flex: 1;
    min-width: 0;

    .line-1 {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 4px;
    }

    .account-name {
      font-size: 16px;
      font-weight: 600;
      color: $text-primary;
      letter-spacing: -0.01em;
    }

    .platform-badge {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 10px;
      font-weight: 500;
      letter-spacing: 0.02em;
    }

    .line-2 {
      display: flex;
      gap: 12px;
      font-size: 12px;
      color: $text-muted;
    }
  }

  .view-link {
    color: $brand-start;
    font-size: 13px;
    text-decoration: none;
    flex-shrink: 0;
    transition: opacity $transition-fast;
    &:hover { text-decoration: underline; opacity: 0.85; }
  }
}

.status-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;

  &.status-success, &.status-partial {
    background: rgba($accent-green, 0.15);
    color: #67c23a;
  }
  &.status-failed {
    background: rgba($danger-color, 0.15);
    color: #f56c6c;
  }
  &.status-running {
    background: rgba($info-color, 0.15);
    color: #409eff;
  }
  &.status-pending, &.status-cancelled {
    background: rgba(0, 0, 0, 0.06);
    color: $text-muted;
  }
}
</style>
