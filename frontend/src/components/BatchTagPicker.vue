<template>
  <div class="batch-section batch-tags">
    <div class="batch-section-header">
      <span class="batch-section-title">选择标签</span>
      <span class="batch-section-count">已选 {{ selectedTagIds.size }}</span>
    </div>

    <div class="batch-tag-create">
      <el-input
        v-model="keyword"
        size="default"
        placeholder="搜索或新建标签..."
        clearable
        @keyup.enter="emit('create')"
      >
        <template #append>
          <el-button :disabled="!keyword.trim()" @click="emit('create')">新建</el-button>
        </template>
      </el-input>
    </div>

    <div class="batch-tag-list">
      <div
        v-for="tag in filteredTags"
        :key="tag.id"
        :class="['batch-tag-chip', { selected: selectedTagIds.has(tag.id) }]"
        :style="selectedTagIds.has(tag.id) ? { background: tag.color, borderColor: tag.color, color: '#fff' } : { borderColor: tag.color, color: tag.color }"
        @click="emit('toggle-tag', tag)"
      >
        <el-icon v-if="selectedTagIds.has(tag.id)" class="batch-tag-check"><Check /></el-icon>
        <span>{{ tag.name }}</span>
        <el-icon
          class="batch-tag-delete"
          title="删除此标签"
          @click.stop="emit('delete-tag', tag)"
        ><Close /></el-icon>
      </div>
      <div v-if="filteredTags.length === 0" class="batch-empty">
        暂无标签,输入名称按回车创建
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, Close } from '@element-plus/icons-vue'

export interface BatchTagItem {
  id: number | string
  name: string
  color?: string
}

const props = defineProps<{
  // 全部可选标签
  tags: BatchTagItem[]
  // 已选标签 id 集合
  selectedTagIds: Set<number | string>
  // 搜索/新建关键词 (v-model)
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: string): void
  (e: 'create'): void
  (e: 'toggle-tag', tag: BatchTagItem): void
  (e: 'delete-tag', tag: BatchTagItem): void
}>()

const keyword = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const filteredTags = computed(() => {
  if (!keyword.value.trim()) return props.tags
  const kw = keyword.value.trim().toLowerCase()
  return props.tags.filter(t => t.name.toLowerCase().includes(kw))
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.batch-section {
  display: flex;
  flex-direction: column;
  background: $bg-surface;
  border: 1px solid $border;
  border-radius: $radius-card;
  overflow: hidden;
}

.batch-tags {
  flex: 1;
}

.batch-section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid $border-light;
  background: rgba($overlay-rgb, 0.02);

  .batch-section-title {
    font-size: 13px;
    font-weight: 600;
    color: $text-primary;
  }

  .batch-section-count {
    font-size: 12px;
    color: $brand-start;
    font-weight: 500;
    padding: 2px 8px;
    background: rgba($brand-start, 0.12);
    border-radius: 10px;
  }
}

// ── 标签区 ──
.batch-tag-create {
  padding: 12px 14px 8px;

  :deep(.el-input__wrapper) {
    background: $bg-surface;
    box-shadow: none;
    border-radius: $radius-sm;
    padding: 2px 12px;
  }

  :deep(.el-input-group__append) {
    background: rgba($brand-start, 0.15);
    .el-button { color: #c4b5fd; font-weight: 500; }
  }
}

.batch-tag-list {
  flex: 1;
  padding: 8px 14px 14px;
  overflow-y: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-content: start;
}

.batch-tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border: 1px solid;
  border-radius: 14px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all $transition-fast;
  background: transparent;
  user-select: none;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);

    .batch-tag-delete {
      opacity: 0.85;
    }
  }

  &.selected {
    font-weight: 600;

    .batch-tag-delete {
      color: #fff !important;
      opacity: 0.85;
    }

    .batch-tag-delete:hover {
      opacity: 1;
      background: rgba($overlay-rgb, 0.2);
    }
  }

  .batch-tag-check { font-size: 12px; }

  .batch-tag-delete {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    margin-left: 2px;
    margin-right: -4px;
    border-radius: 50%;
    font-size: 11px;
    opacity: 0;
    transition: all $transition-fast;
    cursor: pointer;

    &:hover {
      opacity: 1 !important;
      background: rgba($danger-color, 0.85);
      color: #fff !important;
    }
  }
}

.batch-empty {
  grid-column: 1 / -1;
  text-align: center;
  padding: 24px 0;
  color: $text-muted;
  font-size: 13px;
}
</style>
