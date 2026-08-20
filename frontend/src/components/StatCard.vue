<template>
  <div class="stat-card" :class="`stat-${variant}`">
    <div class="stat-top">
      <div class="stat-icon">
        <slot name="icon" />
      </div>
      <div class="stat-info">
        <div class="stat-value">{{ value }}</div>
        <div class="stat-label">{{ label }}</div>
      </div>
      <!-- 可选操作区（如批量检查按钮），由父组件传入 -->
      <slot name="extra" />
    </div>
    <div class="stat-bottom">
      <!-- 默认渲染 key-value 明细；自定义内容（如平台跑马灯）用 #bottom 覆盖 -->
      <slot name="bottom">
        <div v-if="details.length" class="stat-detail">
          <template v-for="(d, i) in details" :key="i">
            <span v-if="i > 0" class="divider"></span>
            <span>{{ d.label }}: {{ d.value }}</span>
          </template>
        </div>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface StatDetail {
  label: string
  value: string | number
}

withDefaults(defineProps<{
  variant: 'purple' | 'blue' | 'cyan' | 'green'
  value: string | number
  label: string
  details?: StatDetail[]
}>(), {
  details: () => [],
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.stat-card {
  border-radius: $radius-card;
  padding: 20px 24px;
  transition: $transition-base;
  min-width: 0;        // 关键: grid cell 默认会被内容撑开
  overflow: hidden;     // 关键: 即使子元素再宽也裁剪掉

  &.stat-purple {
    background: $stat-purple-bg;
    border: 1px solid $stat-purple-border;

    &:hover {
      border-color: rgba($brand-start, 0.35);
      box-shadow: 0 0 24px rgba($brand-start, 0.08);
    }

    .stat-icon {
      background: rgba($brand-start, 0.2);
      :deep(.el-icon) { color: $brand-start; }
    }
  }

  &.stat-blue {
    background: $stat-blue-bg;
    border: 1px solid $stat-blue-border;

    &:hover {
      border-color: rgba($brand-end, 0.35);
      box-shadow: 0 0 24px rgba($brand-end, 0.08);
    }

    .stat-icon {
      background: rgba($brand-end, 0.2);
      :deep(.el-icon) { color: $brand-end; }
    }
  }

  &.stat-cyan {
    background: $stat-cyan-bg;
    border: 1px solid $stat-cyan-border;

    &:hover {
      border-color: rgba($accent-cyan, 0.35);
      box-shadow: 0 0 24px rgba($accent-cyan, 0.08);
    }

    .stat-icon {
      background: rgba($accent-cyan, 0.2);
      :deep(.el-icon) { color: $accent-cyan; }
    }
  }

  &.stat-green {
    background: $stat-green-bg;
    border: 1px solid $stat-green-border;

    &:hover {
      border-color: rgba($accent-green, 0.35);
      box-shadow: 0 0 24px rgba($accent-green, 0.08);
    }

    .stat-icon {
      background: rgba($accent-green, 0.2);
      :deep(.el-icon) { color: $accent-green; }
    }
  }

  .stat-top {
    display: flex;
    align-items: center;
    margin-bottom: 16px;
  }

  .stat-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    background: rgba($overlay-rgb, 0.06);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 16px;
    flex-shrink: 0;

    :deep(.el-icon) {
      font-size: 24px;
    }
  }

  .stat-info {
    .stat-value {
      font-size: 28px;
      font-weight: 700;
      background: $gradient-brand;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      line-height: 1.2;
      letter-spacing: -0.5px;
    }

    .stat-label {
      font-size: 13px;
      color: $text-secondary;
      margin-top: 2px;
    }
  }

  .stat-bottom {
    border-top: 1px solid rgba($overlay-rgb, 0.06);
    padding-top: 12px;
    min-width: 0;          // 关键: 防止 flex 子项把 grid cell 撑开
    overflow: hidden;       // 关键: 强制裁剪, 不让任何子元素跑出 stat-card
  }

  .stat-detail {
    display: flex;
    align-items: center;
    color: $text-secondary;
    font-size: 13px;
    gap: 8px;
    flex-wrap: wrap;

    .divider {
      width: 1px;
      height: 12px;
      background: rgba($overlay-rgb, 0.1);
    }
  }
}
</style>
