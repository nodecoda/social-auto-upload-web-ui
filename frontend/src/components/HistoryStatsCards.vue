<template>
  <div class="stat-cards">
    <div class="stat-card stat-purple">
      <div class="stat-top">
        <div class="stat-icon">
          <el-icon><Upload /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总发布数</div>
        </div>
      </div>
    </div>

    <div class="stat-card stat-blue">
      <div class="stat-top">
        <div class="stat-icon">
          <el-icon><CircleCheck /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.successRate }}%</div>
          <div class="stat-label">成功率</div>
        </div>
      </div>
    </div>

    <div class="stat-card stat-cyan">
      <div class="stat-top">
        <div class="stat-icon">
          <el-icon><Calendar /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.monthlyTotal }}</div>
          <div class="stat-label">本月发布</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Upload, CircleCheck, Calendar } from '@element-plus/icons-vue'

/** 顶部统计卡片 */
export interface StatsSummary {
  total: number
  successRate: number
  monthlyTotal: number
}

defineProps<{
  stats: StatsSummary
}>()
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.stat-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.stat-card {
  border-radius: $radius-card;
  padding: 20px 24px;
  transition: $transition-base;

  &.stat-purple {
    background: $stat-purple-bg;
    border: 1px solid $stat-purple-border;

    &:hover {
      border-color: rgba($brand-start, 0.35);
      box-shadow: 0 0 24px rgba($brand-start, 0.08);
    }

    .stat-icon {
      background: rgba($brand-start, 0.2);
      .el-icon { color: $brand-start; }
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
      .el-icon { color: $brand-end; }
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
      .el-icon { color: $accent-cyan; }
    }
  }

  .stat-top {
    display: flex;
    align-items: center;
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

    .el-icon {
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
}
</style>
