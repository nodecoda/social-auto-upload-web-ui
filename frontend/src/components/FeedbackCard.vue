<template>
  <div class="feedback-card" @click="emit('open', fb)">
    <div class="card-top">
      <el-tag :type="statusTagType(fb.status)" size="small">
        {{ statusLabel(fb.status) }}
      </el-tag>
      <button
        :class="['vote-btn', { voted }]"
        :disabled="voted"
        @click.stop="emit('vote', fb)"
      >
        <el-icon><CaretTop /></el-icon>
        <span>{{ voted ? '已支持' : '我也支持' }}</span>
        <span class="vote-num">{{ fb.vote_count || 0 }}</span>
      </button>
    </div>
    <div class="card-content">{{ truncate(fb.content, 80) }}</div>
    <div class="card-meta">
      <span class="meta-email">{{ maskEmail(fb.email) }}</span>
      <span class="meta-time">{{ formatTime(fb.created_at) }}</span>
    </div>
    <div v-if="fb.attachments && fb.attachments.length" class="card-attachments">
      <el-icon><Paperclip /></el-icon>
      {{ fb.attachments.length }} 个附件
    </div>
  </div>
</template>

<script setup lang="ts">
import { CaretTop, Paperclip } from '@element-plus/icons-vue'

import {
  type FeedbackItem,
  statusLabel,
  statusTagType,
  truncate,
  maskEmail,
  formatTime,
} from '@/components/feedbackShared'

const props = defineProps<{
  fb: FeedbackItem
  voted: boolean
}>()

const emit = defineEmits<{
  (e: 'vote', fb: FeedbackItem): void
  (e: 'open', fb: FeedbackItem): void
}>()
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
.feedback-card {
  padding: 16px;
  border-radius: 12px;
  background: $bg-elevated;
  border: 1px solid $border;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: $brand-start;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  }
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.vote-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid $border;
  background: rgba($overlay-rgb, 0.04);
  color: $text-primary;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;

  &:hover:not(:disabled) {
    border-color: $brand-start;
    color: $brand-start;
    background: rgba($brand-start, 0.1);
    transform: translateY(-1px);
  }

  &:disabled,
  &.voted {
    border-color: $brand-start;
    background: linear-gradient(135deg, $brand-start, $brand-end);
    color: #fff;
    cursor: default;
  }

  .vote-num {
    padding: 0 6px;
    background: rgba(0, 0, 0, 0.15);
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    min-width: 18px;
    text-align: center;
  }

  &:not(.voted) .vote-num {
    background: rgba($overlay-rgb, 0.08);
  }
}

.card-content {
  font-size: 14px;
  line-height: 1.6;
  color: $text-primary;
  margin-bottom: 12px;
  word-break: break-word;
}

.card-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: $text-muted;
  margin-bottom: 8px;
}

.card-attachments {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: $text-muted;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

</style>
