<template>
  <div class="materials-card">
    <div class="materials-header">
      <h2>最近素材</h2>
      <a class="view-all-link" @click="emit('view-all')">查看全部</a>
    </div>

    <el-table
      :data="materials"
      style="width: 100%"
      v-loading="loading"
      :header-cell-style="{ background: 'transparent', borderBottom: `1px solid ${borderColor}` }"
      class="materials-table"
    >
      <el-table-column prop="original_filename" label="文件名" min-width="260">
        <template #default="scope">
          <span class="filename-cell">{{ scope.row.original_filename }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="file_size" label="大小" width="120">
        <template #default="scope">
          <span class="size-cell">{{ (scope.row.file_size / 1024 / 1024).toFixed(2) }} MB</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="100">
        <template #default="scope">
          <span
            class="type-tag"
            :class="{
              'type-video': getFileType(scope.row.file_type) === '视频',
              'type-image': getFileType(scope.row.file_type) === '图片',
              'type-other': getFileType(scope.row.file_type) === '其他'
            }"
          >
            {{ getFileType(scope.row.file_type) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="upload_time" label="上传时间" width="200">
        <template #default="scope">
          <span class="time-cell">{{ scope.row.upload_time }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="!loading && materials.length === 0" class="empty-state">
      暂无素材数据
    </div>
  </div>
</template>

<script setup lang="ts">
export interface MaterialItem {
  id: number | string
  original_filename: string
  file_type: 'image' | 'video' | string
  file_size?: number
  upload_time?: string
}

defineProps<{
  materials: MaterialItem[]
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'view-all'): void
}>()

// 表格边框色（CSS 变量引用，随主题切换）
const borderColor = 'var(--border)'

// 获取文件类型
const FILE_TYPE_MAP: Record<string, string> = { video: '视频', image: '图片' }
const getFileType = (fileType: string): string => FILE_TYPE_MAP[fileType] || '其他'
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.materials-card {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: 24px;
  margin-top: 24px;

  .materials-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;

    h2 {
      font-size: 18px;
      font-weight: 600;
      color: $text-primary;
      margin: 0;
    }

    .view-all-link {
      font-size: 14px;
      color: $brand-start;
      cursor: pointer;
      transition: $transition-base;

      &:hover {
        color: $brand-end;
      }
    }
  }

  .materials-table {
    --el-table-bg-color: transparent;
    --el-table-tr-bg-color: transparent;
    --el-table-header-bg-color: transparent;
    --el-table-row-hover-bg-color: rgba($overlay-rgb, 0.03);
    --el-table-border-color: #{$border};
    --el-table-text-color: #{$text-secondary};
    --el-table-header-text-color: #{$text-muted};

    :deep(.el-table__inner-wrapper) {
      &::before {
        display: none;
      }
    }

    :deep(th.el-table__cell) {
      background: transparent !important;
      font-weight: 500;
      font-size: 13px;
      border-bottom: 1px solid $border;
    }

    :deep(td.el-table__cell) {
      border-bottom: 1px solid rgba($overlay-rgb, 0.04);
    }

    :deep(.el-table__empty-block) {
      background: transparent;
    }
  }

  .filename-cell {
    color: $text-primary;
    font-weight: 500;
  }

  .size-cell {
    color: $text-secondary;
  }

  .time-cell {
    color: $text-secondary;
    font-size: 13px;
  }

  .type-tag {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;

    &.type-video {
      color: $accent-green;
      background: rgba($accent-green, 0.12);
    }

    &.type-image {
      color: $accent-amber;
      background: rgba($accent-amber, 0.12);
    }

    &.type-other {
      color: $text-muted;
      background: rgba($overlay-rgb, 0.06);
    }
  }

  .empty-state {
    text-align: center;
    color: $text-muted;
    padding: 40px 0;
    font-size: 14px;
  }
}
</style>
