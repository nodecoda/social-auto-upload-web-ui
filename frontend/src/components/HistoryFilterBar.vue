<template>
  <div class="filter-card">
    <div class="filter-row">
      <div class="filter-controls">
        <el-select
          :model-value="timeRange"
          placeholder="时间范围"
          class="filter-select"
          @update:model-value="setFilter('timeRange', $event)"
        >
          <el-option label="今天" value="today" />
          <el-option label="最近7天" value="7days" />
          <el-option label="最近30天" value="30days" />
          <el-option label="全部" value="all" />
        </el-select>

        <el-select
          :model-value="typeFilter"
          placeholder="类型"
          class="filter-select"
          @update:model-value="setFilter('typeFilter', $event)"
        >
          <el-option label="全部" value="all" />
          <el-option label="视频" value="video" />
          <el-option label="图集" value="image" />
        </el-select>

        <el-select
          :model-value="platformFilter"
          placeholder="平台"
          class="filter-select"
          @update:model-value="setFilter('platformFilter', $event)"
        >
          <el-option label="全部" value="all" />
          <el-option v-for="p in platformList" :key="p.key" :label="p.name" :value="p.key" />
        </el-select>

        <el-select
          :model-value="statusFilter"
          placeholder="状态"
          class="filter-select"
          @update:model-value="setFilter('statusFilter', $event)"
        >
          <el-option label="全部" value="all" />
          <el-option label="全部成功" value="success" />
          <el-option label="部分失败" value="partial" />
          <el-option label="全部失败" value="failed" />
        </el-select>
      </div>

      <div class="filter-actions">
        <el-button
          v-if="!selectMode"
          class="select-trigger-btn"
          :icon="Select"
          :disabled="batchesCount === 0"
          @click="emit('select-mode-toggle')"
        >
          多选
        </el-button>
        <el-button
          class="refresh-btn"
          :icon="Refresh"
          @click="emit('refresh')"
          :loading="loading"
        >
          刷新
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Select, Refresh } from '@element-plus/icons-vue'
import { platformList } from '@/config/platforms'

defineProps<{
  timeRange: string
  typeFilter: string
  platformFilter: string
  statusFilter: string
  selectMode: boolean
  batchesCount: number
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'update:timeRange', v: string): void
  (e: 'update:typeFilter', v: string): void
  (e: 'update:platformFilter', v: string): void
  (e: 'update:statusFilter', v: string): void
  (e: 'change'): void
  (e: 'select-mode-toggle'): void
  (e: 'refresh'): void
}>()

function setFilter(key: 'timeRange' | 'typeFilter' | 'platformFilter' | 'statusFilter', value: string) {
  if (key === 'timeRange') emit('update:timeRange', value)
  else if (key === 'typeFilter') emit('update:typeFilter', value)
  else if (key === 'platformFilter') emit('update:platformFilter', value)
  else emit('update:statusFilter', value)
  emit('change')
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
.filter-card {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: 16px 20px;
  margin-top: 24px;

  .filter-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }

  .filter-controls {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .filter-select {
    width: 140px;

    :deep(.el-input__wrapper) {
      background: rgba($overlay-rgb, 0.04);
      border: 1px solid $border;
      border-radius: $radius-base;
      box-shadow: none;

      &:hover {
        border-color: $border-active;
      }

      &.is-focus {
        border-color: $brand-start;
      }
    }

    :deep(.el-input__inner) {
      color: $text-secondary;
      font-size: 13px;
    }

    :deep(.el-input__suffix) {
      color: $text-muted;
    }
  }

  .refresh-btn {
    background: rgba($overlay-rgb, 0.04);
    border: 1px solid $border;
    border-radius: $radius-base;
    color: $text-secondary;
    font-size: 13px;

    &:hover {
      border-color: $border-active;
      color: $brand-start;
      background: rgba($brand-start, 0.06);
    }
  }

  .filter-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .select-trigger-btn {
    background: rgba($overlay-rgb, 0.04);
    border: 1px solid $border;
    border-radius: $radius-base;
    color: $text-secondary;
    font-size: 13px;

    &:hover {
      border-color: rgba($brand-start, 0.4);
      color: lighten($brand-start, 12%);
      background: rgba($brand-start, 0.1);
    }

    &.is-disabled,
    &.is-disabled:hover {
      opacity: 0.5;
      background: rgba($overlay-rgb, 0.04);
      border-color: $border;
      color: $text-muted;
    }
  }
}

</style>
