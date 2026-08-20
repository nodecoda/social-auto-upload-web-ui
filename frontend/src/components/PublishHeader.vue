<template>
  <div class="main-header">
    <div class="header-left">
      <span class="page-title">{{ title }}</span>
      <span
        v-if="platformName"
        class="platform-tag"
        :style="{ background: platformBgColor, color: platformColor }"
      >
        {{ platformName }} · 个性化设置
      </span>
    </div>
    <div class="header-right">
      <el-button :icon="Document" @click="$emit('save-draft')" class="header-btn">
        {{ draftId ? '更新草稿' : '保存草稿' }}
      </el-button>
      <el-button :icon="MagicStick" @click="$emit('one-click')" :disabled="disableOneClick" class="header-btn">
        一键填写
      </el-button>
      <el-button :icon="Setting" @click="$emit('batch-set')" :disabled="!hasAccounts" class="header-btn">
        批量设置
      </el-button>
      <el-button type="primary" :icon="Promotion" @click="$emit('publish')" :disabled="publishing" class="header-btn header-btn--primary">
        {{ publishing ? '发布中...' : '一键发布' }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Document, MagicStick, Setting, Promotion } from '@element-plus/icons-vue'

withDefaults(defineProps<{
  title?: string
  platformName?: string
  platformBgColor?: string
  platformColor?: string
  draftId?: string | number | null
  hasAccounts?: boolean
  publishing?: boolean
  // 无账号时禁用一键填写（图集发布需要账号才能填充渠道配置）
  disableOneClick?: boolean
}>(), {
  title: '发布视频',
  platformName: '',
  platformBgColor: '',
  platformColor: '',
  draftId: null,
  hasAccounts: false,
  publishing: false,
  disableOneClick: false,
})

defineEmits<{
  (e: 'save-draft'): void
  (e: 'one-click'): void
  (e: 'batch-set'): void
  (e: 'publish'): void
}>()
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
.main-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 28px;
  border-bottom: 1px solid rgba($overlay-rgb, 0.06);
  flex-shrink: 0;
  background: linear-gradient(90deg, rgba($brand-start, 0.04) 0%, transparent 40%, transparent 60%, rgba($info-color, 0.03) 100%);

  .header-left {
    display: flex;
    align-items: center;
    gap: 14px;

    .page-title {
      font-size: 20px;
      font-weight: 800;
      color: $popper-text;
      letter-spacing: -0.02em;
    }

    .platform-tag {
      font-size: 12px;
      font-weight: 600;
      padding: 5px 16px;
      border-radius: 20px;
      letter-spacing: 0.02em;
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: flex-end;

    .header-btn {
      // el-button 默认 padding 8px 15px / font-size 14px / height 32px
      // 想要更紧凑一点,小分辨率下自动缩
      @media (max-width: 1280px) {
        padding: 6px 12px !important;
        font-size: 12px !important;
      }
    }

    .header-btn--primary {
      // 一键发布: 保留项目渐变 + 阴影
      background: linear-gradient(135deg, #8b5cf6, #6366f1) !important;
      border: none !important;
      box-shadow: 0 4px 20px rgba($brand-start, 0.35) !important;
      font-weight: 700;
      letter-spacing: 0.04em;
      padding: 10px 24px !important;

      &:hover {
        box-shadow: 0 6px 28px rgba($brand-start, 0.5) !important;
        transform: translateY(-1px);
        opacity: 1 !important;
      }
      &:active { transform: translateY(0) scale(0.98); }
      &:disabled { opacity: 0.5 !important; cursor: not-allowed; transform: none; box-shadow: none !important; }
    }
  }
}
</style>
