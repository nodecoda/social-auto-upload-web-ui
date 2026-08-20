<template>
  <el-dialog
    v-model="visible"
    :width="920"
    :close-on-click-modal="false"
    class="material-select-dialog"
    destroy-on-close
    @closed="onClosed"
    append-to-body
  >
    <template #header>
      <div class="msd-header">
        <div class="msd-header-title">
          <span class="msd-header-dot" />
          <span>选择素材</span>
        </div>
        <div class="msd-header-stats">
          共 <b>{{ total }}</b> 个素材
          <span v-if="hasFilter" class="msd-header-filter-hint">（已筛选）</span>
        </div>
      </div>
    </template>

    <!-- Toolbar: search + type filter -->
    <div class="msd-toolbar">
      <div class="msd-search">
        <el-input
          v-model="searchKeyword"
          placeholder="按文件名搜索..."
          clearable
          :prefix-icon="Search"
          @input="onSearchInput"
          @clear="onSearchClear"
        />
      </div>
      <div class="msd-type-filter">
        <button
          v-for="opt in typeOptions"
          :key="opt.value"
          :class="['msd-type-btn', { active: typeFilter === opt.value }]"
          @click="onTypeChange(opt.value)"
        >
          <el-icon :size="14"><component :is="opt.icon" /></el-icon>
          <span>{{ opt.label }}</span>
        </button>
      </div>
    </div>

    <!-- Body -->
    <div class="msd-body" v-loading="loading">
    <div v-if="items.length > 0" class="msd-grid">
      <MaterialCard
        v-for="mat in items"
        :key="mat.id"
        :mat="mat"
        :selected="selectedId === mat.id"
        :playing="playingId === mat.id"
        @select="selectedId = mat.id"
        @toggle-play="togglePlay(mat.id)"
        @video-ended="onVideoEnded(mat.id)"
      />
    </div>

      <div v-else-if="!loading" class="msd-empty">
        <div class="msd-empty-icon">
          <el-icon :size="48"><Picture /></el-icon>
        </div>
        <div class="msd-empty-title">
          {{ hasFilter ? '没有匹配的素材' : '素材库还是空的' }}
        </div>
        <div class="msd-empty-desc">
          {{ hasFilter ? '试试其他关键词或类型' : '上传你的第一个素材吧' }}
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="total > 0" class="msd-pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[12, 24, 48, 96]"
        :total="total"
        layout="sizes, prev, pager, next, jumper"
        background
        small
        @current-change="loadPage"
        @size-change="onPageSizeChange"
      />
    </div>

    <template #footer>
      <div class="msd-footer">
        <div class="msd-footer-status">
          <span v-if="selectedMat" class="msd-footer-selected">
            <el-icon :size="14" color="var(--brand-start, #5b8cff)"><Check /></el-icon>
            <span>已选：{{ selectedMat.original_filename }}</span>
          </span>
          <span v-else class="msd-footer-hint">未选择素材</span>
        </div>
        <div class="msd-footer-actions">
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" :disabled="!selectedId" :loading="probing" @click="confirmSelect">
            确定
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, type PropType } from 'vue'
import {
  Search,
  Check,
  Picture,
  PictureFilled,
  VideoCamera,
  Grid,
} from '@element-plus/icons-vue'
import MaterialCard from './MaterialCard.vue'
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'

interface MaterialItem {
  id: number | string
  original_filename: string
  file_type: 'image' | 'video' | string
  mime_type?: string
  stored_path: string
  thumbnail_url?: string
  storage_type?: string
  file_size?: number
  duration?: number
  upload_time?: string
}

interface MaterialListResponse {
  code?: number
  data?: { items?: MaterialItem[]; total?: number }
}

const props = withDefaults(defineProps<{
  /** 'all' | 'image' | 'video' - 限制可选项，默认 'all' */
  filterType?: string
  /** 多选模式：返回数组；单选模式：返回单个 */
  multiple?: boolean
}>(), {
  filterType: 'all',
  multiple: false,
})

const emit = defineEmits<{
  (e: 'select', payload: { id: number | string; name: string; url: string; stored_path: string; size?: number; type?: string; duration?: number }): void
}>()

const visible = ref(false)
const loading = ref(false)
const probing = ref(false)
const items = ref<MaterialItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(24)
const searchKeyword = ref('')
const typeFilter = ref('all')
const selectedId = ref<number | string | null>(null)
// 当前正在播放的视频素材 id（互斥，同一时间只能播一个）
const playingId = ref<number | string | null>(null)

// 当 props.filterType 限定为 video/image 时，只显示对应按钮，不允许切换类型
const typeOptions = computed(() => {
  if (props.filterType === 'video') {
    return [{ value: 'video', label: '视频', icon: VideoCamera }]
  }
  if (props.filterType === 'image') {
    return [{ value: 'image', label: '图片', icon: PictureFilled }]
  }
  return [
    { value: 'all', label: '全部', icon: Grid },
    { value: 'image', label: '图片', icon: PictureFilled },
    { value: 'video', label: '视频', icon: VideoCamera },
  ]
})

const hasFilter = computed(
  () => searchKeyword.value.trim() !== '' || typeFilter.value !== props.filterType,
)

const selectedMat = computed<MaterialItem | null>(
  () => items.value.find((m) => m.id === selectedId.value) || null,
)

function togglePlay(id: number | string) {
  playingId.value = playingId.value === id ? null : id
}

function onVideoEnded(id: number | string) {
  if (playingId.value === id) {
    playingId.value = null
  }
}

// 预编码的 fallback SVG（占位图），用于图片加载失败时
let searchDebounce: ReturnType<typeof setTimeout> | null = null
function onSearchInput() {
  clearTimeout(searchDebounce ?? undefined)
  searchDebounce = setTimeout(() => {
    page.value = 1
    loadPage()
  }, 300)
}

function onSearchClear() {
  page.value = 1
  loadPage()
}

function onTypeChange(value: string) {
  typeFilter.value = value
  page.value = 1
  loadPage()
}

function onPageSizeChange() {
  page.value = 1
  loadPage()
}

async function loadPage() {
  loading.value = true
  try {
    const resp = (await materialsApi.list({
      type: typeFilter.value,
      keyword: searchKeyword.value.trim(),
      page: page.value,
      page_size: pageSize.value,
    })) as MaterialListResponse
    if (resp.code === 200) {
      items.value = resp.data?.items || []
      total.value = resp.data?.total || 0
      // 翻页后，如果当前选中/正在播放的素材不在新页面则清空
      if (selectedId.value && !items.value.some((m) => m.id === selectedId.value)) {
        selectedId.value = null
      }
      if (playingId.value && !items.value.some((m) => m.id === playingId.value)) {
        playingId.value = null
      }
    }
  } catch (e) {
    console.error('加载素材失败:', e)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function confirmSelect() {
  if (!selectedId.value) return
  const material = items.value.find((m) => m.id === selectedId.value)
  if (!material) return

  // 视频且元数据缺失（duration=0）时,同步调用 /probe 补全元数据,
  // 这样调用方在 publishAll 校验时拿到的 videoData 已含 duration
  if (material.file_type === 'video' && (!material.duration || material.duration === 0)) {
    try {
      probing.value = true
      const res = (await materialsApi.probe(material.id)) as
        { code?: number; data?: { duration?: number; file_size?: number } } | undefined
      if (res?.code === 200 && res.data) {
        // 用后端返回的最新数据更新 material
        Object.assign(material, {
          duration: res.data.duration,
          file_size: res.data.file_size,
        })
      }
    } catch (err) {
      console.warn('[MaterialSelectDialog] probe failed:', err)
      // probe 失败也允许继续选,前端校验会兜底
    } finally {
      probing.value = false
    }
  }

  emit('select', {
    id: material.id,
    name: material.original_filename,
    url: getFileUrl(material.stored_path),
    stored_path: material.stored_path,
    size: material.file_size,
    type: material.mime_type,
    duration: material.duration ?? 0,
  })
  visible.value = false
}

function onClosed() {
  searchKeyword.value = ''
  typeFilter.value = props.filterType || 'all'
  page.value = 1
  selectedId.value = null
  playingId.value = null
  items.value = []
  total.value = 0
}

async function open() {
  visible.value = true
  typeFilter.value = props.filterType || 'all'
  page.value = 1
  selectedId.value = null
  await loadPage()
}

defineExpose({ open })
</script>

<style lang="scss">
@use '@/styles/variables.scss' as *;
.material-select-dialog {
  --msd-radius: 14px;
  --msd-glass: rgba($bg-elevated-rgb, 0.85);
  --msd-border: rgba($overlay-rgb, 0.08);
  --msd-brand-1: #5b8cff;
  --msd-brand-2: #8b5cff;

  .el-dialog {
    background: var(--msd-glass);
    backdrop-filter: blur(20px) saturate(140%);
    -webkit-backdrop-filter: blur(20px) saturate(140%);
    border: 1px solid var(--msd-border);
    border-radius: var(--msd-radius);
    box-shadow:
      0 25px 60px rgba(0, 0, 0, 0.5),
      0 0 0 1px rgba($overlay-rgb, 0.03),
      inset 0 1px 0 rgba($overlay-rgb, 0.04);
    overflow: hidden;
  }

  .el-dialog__header {
    padding: 0;
    margin-right: 0;
  }

  .el-dialog__body {
    padding: 0;
    background: var(--msd-glass);
  }

  .el-dialog__footer {
    padding: 14px 20px;
    border-top: 1px solid var(--msd-border);
    background: $bg-base;
  }
}
</style>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;
$brand-1: #5b8cff;
$brand-2: #8b5cff;
$text-1: $text-primary;
$text-2: $text-secondary;
$text-3: $text-muted;
$border: rgba($overlay-rgb, 0.08);
$bg-card: rgba($overlay-rgb, 0.03);
$bg-card-hover: rgba($overlay-rgb, 0.05);

// ===== Header =====
.msd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid $border;
}

.msd-header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  color: $text-1;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.msd-header-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, $brand-1, $brand-2);
  box-shadow: 0 0 8px rgba($brand-1, 0.4);
}

.msd-header-stats {
  font-size: 12px;
  color: $text-2;

  b {
    color: $text-1;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
}

.msd-header-filter-hint {
  margin-left: 4px;
  color: $brand-1;
}

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

// ===== Body =====
.msd-body {
  padding: 12px 16px 4px;
  min-height: 320px;
  max-height: 52vh;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba($overlay-rgb, 0.08) transparent;

  &::-webkit-scrollbar { width: 6px; }
  &::-webkit-scrollbar-thumb {
    background: rgba($overlay-rgb, 0.1);
    border-radius: 3px;
    &:hover { background: rgba($overlay-rgb, 0.18); }
  }
}

// ===== Grid =====
.msd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 10px;
  padding: 4px 0 12px;
}

// ===== Card =====
// ===== Empty =====
.msd-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 60px 0;
  color: $text-2;
}

.msd-empty-icon {
  color: $text-3;
  opacity: 0.5;
  margin-bottom: 4px;
}

.msd-empty-title {
  font-size: 13px;
  color: $text-1;
  font-weight: 500;
}

.msd-empty-desc {
  font-size: 12px;
  color: $text-3;
}

// ===== Pagination =====
.msd-pagination {
  display: flex;
  justify-content: center;
  padding: 10px 16px;
  border-top: 1px solid $border;
  margin: 4px 0 0;

  :deep(.el-pagination) {
    --el-pagination-bg-color: transparent;
    --el-pagination-button-bg-color: rgba($overlay-rgb, 0.04);
    --el-pagination-hover-color: #{$brand-1};
    --el-pagination-button-color: #{$text-2};
    --el-pagination-button-disabled-bg-color: transparent;

    .btn-prev, .btn-next, .el-pager li {
      background: rgba($overlay-rgb, 0.04) !important;
      color: $text-2 !important;
      border: 1px solid transparent;
      border-radius: 6px;

      &:hover {
        color: $brand-1 !important;
        border-color: rgba($brand-1, 0.3);
      }
    }

    .el-pager li.is-active {
      background: linear-gradient(135deg, $brand-1, $brand-2) !important;
      color: #fff !important;
      border-color: transparent;
    }

    .el-pagination__sizes .el-select .el-select__wrapper {
      background: rgba($overlay-rgb, 0.04);
      box-shadow: 0 0 0 1px $border;
    }
  }
}

// ===== Footer =====
.msd-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.msd-footer-status {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: $text-2;
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
}

.msd-footer-selected {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: $text-1;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;

  span:last-child {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.msd-footer-hint {
  color: $text-3;
}

.msd-footer-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;

  :deep(.el-button--primary) {
    background: linear-gradient(135deg, $brand-1, $brand-2);
    border: none;
    box-shadow: 0 2px 10px rgba($brand-1, 0.3);
    &:hover {
      opacity: 0.92;
      box-shadow: 0 4px 14px rgba($brand-1, 0.4);
    }
    &.is-disabled {
      opacity: 0.4;
      background: linear-gradient(135deg, $brand-1, $brand-2);
    }
  }
}
</style>
