<template>
  <div class="main-header">
    <div class="header-left">
      <span class="page-title">发布视频</span>
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
      <el-button :icon="MagicStick" @click="$emit('one-click')" class="header-btn">
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

<script setup>
import { Document, MagicStick, Setting, Promotion } from '@element-plus/icons-vue'

defineProps({
  platformName: { type: String, default: '' },
  platformBgColor: { type: String, default: '' },
  platformColor: { type: String, default: '' },
  draftId: { type: [String, Number], default: null },
  hasAccounts: { type: Boolean, default: false },
  publishing: { type: Boolean, default: false },
})

defineEmits(['save-draft', 'one-click', 'batch-set', 'publish'])
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
.main-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid $border;
  flex-shrink: 0;

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;

    .page-title {
      font-size: 18px;
      font-weight: 700;
      color: $text-primary;
    }

    .platform-tag {
      font-size: 12px;
      font-weight: 500;
      padding: 4px 12px;
      border-radius: 20px;
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
