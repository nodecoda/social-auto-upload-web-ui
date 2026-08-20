<template>
  <div class="batch-toolbar">
    <el-checkbox
      :model-value="isAllSelected"
      :indeterminate="isIndeterminate"
      class="toolbar-select-all"
      @change="emit('toggle-select-all', $event)"
    >
      全选
    </el-checkbox>

    <div class="selected-info">
      <el-icon class="selected-icon"><Check /></el-icon>
      <span>已选 <strong>{{ selectionSize }}</strong> / {{ totalCount }}</span>
    </div>

    <div class="toolbar-spacer"></div>

    <el-button
      size="default"
      :icon="Delete"
      type="danger"
      :disabled="selectionSize === 0 || isDeleting"
      @click="emit('batch-delete')"
    >
      批量删除<template v-if="selectionSize > 0"> ({{ selectionSize }})</template>
    </el-button>
    <el-button
      size="default"
      :icon="Close"
      class="toolbar-exit"
      @click="emit('exit-select-mode')"
    >
      退出多选
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { Check, Delete, Close } from '@element-plus/icons-vue'

defineProps<{
  isAllSelected: boolean
  isIndeterminate: boolean
  selectionSize: number
  totalCount: number
  isDeleting: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-select-all', checked: boolean | string | number): void
  (e: 'batch-delete'): void
  (e: 'exit-select-mode'): void
}>()
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
.batch-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-radius: $radius-card;
  border: 1px solid $border-active;
  background: linear-gradient(135deg, rgba($brand-start, 0.1), rgba($brand-end, 0.06));
  box-shadow: 0 0 24px rgba($brand-start, 0.08);
  backdrop-filter: blur(8px);
}

.toolbar-select-all {
  :deep(.el-checkbox__label) {
    color: $text-secondary;
    font-size: 13px;
  }
}

.toolbar-spacer {
  flex: 1;
}

.selected-info {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: linear-gradient(135deg, rgba($brand-start, 0.18), rgba($brand-end, 0.12));
  border: 1px solid rgba($brand-start, 0.25);
  color: lighten($brand-start, 12%);
  font-size: 13px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;

  .selected-icon {
    font-size: 12px;
    color: $brand-start;
  }

  strong {
    color: $text-primary;
    font-weight: 600;
  }
}

.toolbar-exit {
  --el-button-bg-color: rgba($overlay-rgb, 0.03);
  --el-button-border-color: rgba($overlay-rgb, 0.12);
  --el-button-text-color: $text-secondary;
  --el-button-hover-bg-color: rgba($accent-rose, 0.12);
  --el-button-hover-border-color: rgba($accent-rose, 0.4);
  --el-button-hover-text-color: lighten($accent-rose, 8%);
}

</style>
