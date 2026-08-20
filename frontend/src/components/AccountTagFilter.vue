<template>
  <div class="account-section tag-section">
    <div class="account-section-header">
      <span class="account-section-title">标签筛选</span>
      <span class="account-section-count">已选 {{ selectedTagIds.size }}</span>
      <el-button
        size="small"
        link
        type="primary"
        class="ml-auto"
        :disabled="selectedTagIds.size === 0"
        @click="emit('clear-all')"
      >全不选</el-button>
    </div>

    <div v-if="allTags.length > 0" class="tag-search">
      <el-input
        v-model="keyword"
        size="default"
        placeholder="搜索标签..."
        clearable
      />
    </div>

    <div class="tag-list">
      <div
        v-for="tag in filteredTags"
        :key="tag.id"
        :class="['tag-chip', { selected: selectedTagIds.has(tag.id) }]"
        :style="selectedTagIds.has(tag.id)
          ? { background: tag.color, borderColor: tag.color, color: '#fff' }
          : { borderColor: tag.color, color: tag.color }"
        @click="emit('toggle-tag', tag.id)"
      >
        <el-icon v-if="selectedTagIds.has(tag.id)" class="tag-check"><Check /></el-icon>
        <span>{{ tag.name }}</span>
      </div>
      <div v-if="allTags.length === 0" class="empty-hint">暂无标签</div>
      <div v-else-if="filteredTags.length === 0" class="empty-hint">没有匹配的标签</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check } from '@element-plus/icons-vue'

interface AccountTag {
  id: number | string
  name: string
  color?: string
}

const props = defineProps<{
  // 全部可选标签
  allTags: AccountTag[]
  // 已选标签 id 集合
  selectedTagIds: Set<number | string>
  // 搜索关键词 (v-model)
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: string): void
  (e: 'toggle-tag', id: number | string): void
  (e: 'clear-all'): void
}>()

const keyword = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const filteredTags = computed<AccountTag[]>(() => {
  const all = props.allTags || []
  if (!keyword.value.trim()) return all
  const kw = keyword.value.trim().toLowerCase()
  return all.filter(t => t.name.toLowerCase().includes(kw))
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.account-section {
  display: flex;
  flex-direction: column;
  background: $bg-base;
  border: 1px solid $border;
  border-radius: $radius-card;
  overflow: hidden;
}

.tag-section {
  flex: 1;
  min-width: 220px;
}

.account-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid $border-light;
  background: rgba($overlay-rgb, 0.02);
  flex-shrink: 0;

  .account-section-title {
    font-size: 13px;
    font-weight: 600;
    color: $text-primary;
  }

  .account-section-count {
    font-size: 12px;
    color: $brand-start;
    font-weight: 500;
    padding: 2px 8px;
    background: rgba($brand-start, 0.12);
    border-radius: 10px;
  }
}

.tag-search {
  padding: 12px 12px 4px;
  flex-shrink: 0;

  :deep(.el-input__wrapper) {
    background: $bg-surface;
    box-shadow: none;
    border-radius: $radius-sm;
    padding: 2px 12px;
  }
}

.tag-list {
  flex: 1;
  padding: 8px 12px 12px;
  overflow-y: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-content: start;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
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
  }

  &.selected {
    font-weight: 600;
  }

  .tag-check { font-size: 12px; }
}

.empty-hint {
  width: 100%;
  text-align: center;
  padding: 24px 0;
  color: $text-muted;
  font-size: 13px;
}
</style>
