<template>
  <div class="msd-toolbar">
    <div class="msd-search">
      <el-input
        v-model="keyword"
        placeholder="按文件名搜索..."
        clearable
        :prefix-icon="Search"
        @input="emit('search-input')"
        @clear="emit('search-clear')"
      />
    </div>
    <div class="msd-type-filter">
      <button
        v-for="opt in typeOptions"
        :key="opt.value"
        :class="['msd-type-btn', { active: typeFilter === opt.value }]"
        @click="emit('type-change', opt.value)"
      >
        <el-icon :size="14"><component :is="opt.icon" /></el-icon>
        <span>{{ opt.label }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Search } from '@element-plus/icons-vue'

export interface MaterialSelectTypeOption {
  value: string
  label: string
  icon: Component
}

const props = defineProps<{
  // 搜索关键词 (v-model)
  modelValue: string
  // 类型筛选按钮选项
  typeOptions: MaterialSelectTypeOption[]
  // 当前激活的类型
  typeFilter: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: string): void
  (e: 'search-input'): void
  (e: 'search-clear'): void
  (e: 'type-change', val: string): void
}>()

const keyword = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

// 源组件(MaterialSelectDialog)自定义变量,拆分后需随样式复制
$brand-1: #5b8cff;
$brand-2: #8b5cff;
$text-1: $text-primary;
$text-2: $text-secondary;
$text-3: $text-muted;
$border: rgba($overlay-rgb, 0.08);
$bg-card-hover: rgba($overlay-rgb, 0.05);

// ===== Toolbar（独立容器，搜索 + 分段控件） =====
.msd-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  margin: 12px 16px 0;
  background: $overlay-hover;
  border: 1px solid $border;
  border-radius: 12px;
}

.msd-search {
  flex: 1;
  max-width: 320px;

  :deep(.el-input__wrapper) {
    background: $bg-elevated;
    border: 1px solid transparent;
    border-radius: 20px;
    box-shadow: none;
    padding: 6px 14px;
    transition: all 0.2s ease;
    &:hover { border-color: rgba($overlay-rgb, 0.16); }
    &.is-focus {
      border-color: rgba($brand-1, 0.5);
      box-shadow: 0 0 0 3px rgba($brand-1, 0.12);
    }
    .el-input__inner {
      height: 28px;
      color: $text-1;
      &::placeholder { color: $text-3; }
    }
    .el-input__prefix .el-icon { color: $text-2; }
  }
}

// 类型筛选：分段控件（segmented control）风格
.msd-type-filter {
  display: flex;
  gap: 2px;
  padding: 3px;
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: 10px;
}

.msd-type-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  background: transparent;
  border: none;
  border-radius: 7px;
  color: $text-2;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover { color: $text-1; background: $bg-card-hover; }

  &.active {
    color: #fff;
    background: linear-gradient(135deg, rgba($brand-1, 0.9), rgba($brand-2, 0.9));
    box-shadow: 0 2px 8px rgba($brand-1, 0.3);
  }
}
</style>
