<template>
  <div class="image-uploader">
    <!-- Header with count -->
    <div class="uploader-header">
      <div class="uploader-title">
        <span class="title-dot"></span>
        <span>图片列表</span>
      </div>
      <span class="uploader-count">已上传 {{ images.length }}/{{ maxCount }} 张</span>
    </div>

    <!-- Image grid -->
    <div
      class="image-grid"
      ref="gridRef"
      :class="{ 'has-scroll': images.length > visibleRows * columns }"
    >
      <ImageGridItem
        v-for="(image, index) in images"
        :key="image.id || index"
        :image="image"
        :index="index"
        @re-upload="reUpload"
        @open-material-library="openMaterialLibrary"
        @remove="removeImage"
      />

      <!-- Upload button -->
      <div
        v-if="images.length < maxCount"
        class="upload-trigger-wrapper"
      >
        <div
          class="upload-trigger"
          @click="triggerUpload"
          @dragover.prevent="onDragOver"
          @dragleave="onDragLeave"
          @drop.prevent="onDrop"
          :class="{ 'drag-over': isDragOver }"
        >
          <el-icon :size="28"><Plus /></el-icon>
          <span class="upload-text">上传图片</span>
          <span class="upload-hint">支持拖拽上传</span>
        </div>
        <div class="upload-placeholder-name"></div>
      </div>
    </div>

    <!-- Hidden file input -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      multiple
      style="display: none"
      @change="onFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, type PropType } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import ImageGridItem, { type UploadImageItem } from './ImageGridItem.vue'
// @ts-ignore
import Sortable from 'sortablejs'
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'
import type { AxiosProgressEvent } from 'axios'

interface UploadRespData {
  id: number | string
  original_filename: string
  stored_path: string
  file_size: number
  mime_type: string
}

const props = defineProps({
  modelValue: { type: Array as PropType<UploadImageItem[]>, default: (): any[] => [] },
  maxCount: { type: Number, default: 35 },
  visibleRows: { type: Number, default: 3 },
  columns: { type: Number, default: 5 },
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: UploadImageItem[]): void
  (e: 'open-material-library', index: number): void
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const gridRef = ref<HTMLElement | null>(null)
const isDragOver = ref(false)
let sortableInstance: Sortable | null = null

// Local copy of images for two-way binding
const images = ref<UploadImageItem[]>([])

// Sync with parent
watch(() => props.modelValue, (newVal) => {
  images.value = newVal || []
}, { immediate: true, deep: true })

// Emit changes back to parent
watch(images, (newVal) => {
  emit('update:modelValue', newVal)
}, { deep: true })

// Initialize SortableJS
onMounted(() => {
  initSortable()
})

onBeforeUnmount(() => {
  if (sortableInstance) {
    sortableInstance.destroy()
    sortableInstance = null
  }
})

function initSortable() {
  if (!gridRef.value) return

  sortableInstance = Sortable.create(gridRef.value, {
    animation: 200,
    handle: '.sort-handle',
    ghostClass: 'sortable-ghost',
    chosenClass: 'sortable-chosen',
    dragClass: 'sortable-drag',
    filter: '.upload-trigger',
    onEnd(evt: any) {
      const { oldIndex, newIndex } = evt
      if (oldIndex === newIndex) return

      // Reorder the array
      const movedItem = images.value.splice(oldIndex, 1)[0]
      images.value.splice(newIndex, 0, movedItem)
    },
  })
}

// Trigger file input click
function triggerUpload() {
  fileInputRef.value?.click()
}

// Handle file selection
function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (!files.length) return

  const remainingSlots = props.maxCount - images.value.length
  const filesToUpload = files.slice(0, remainingSlots)

  if (files.length > remainingSlots) {
    ElMessage.warning(`最多只能上传 ${props.maxCount} 张图片，已自动截取前 ${remainingSlots} 张`)
  }

  filesToUpload.forEach(file => uploadFile(file))

  // Reset input
  input.value = ''
}

// Upload a single file
async function uploadFile(file: File) {
  const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/bmp']
  if (!validTypes.includes(file.type)) {
    ElMessage.warning('不支持的图片格式')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 10MB')
    return
  }

  const placeholder: UploadImageItem = {
    id: `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: file.name,
    url: URL.createObjectURL(file),
    stored_path: '',
    size: file.size,
    type: file.type,
    uploading: true,
    progress: 0,
  }
  images.value.push(placeholder)
  const index = images.value.length - 1

  try {
    const formData = new FormData()
    formData.append('file', file)
    // materialsApi.upload 返回类型未精确标注, 按响应结构做最小标注
    const resp = (await materialsApi.upload(formData, (e: AxiosProgressEvent) => {
      if (images.value[index] && e.progress != null) {
        images.value[index].progress = Math.round(e.progress * 100)
      }
    })) as { code?: number; data?: UploadRespData }
    if (resp.code === 200) {
      const d = resp.data as UploadRespData
      images.value[index] = {
        id: d.id,
        name: d.original_filename,
        url: getFileUrl(d.stored_path),
        stored_path: d.stored_path,
        size: d.file_size,
        type: d.mime_type,
        uploading: false,
        progress: 100,
      }
    }
  } catch {
    images.value.splice(index, 1)
    ElMessage.error('图片上传失败')
  }
}

// Remove image
function removeImage(index: number) {
  images.value.splice(index, 1)
}

// Re-upload image
function reUpload(index: number) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/jpeg,image/png,image/webp'
  input.onchange = (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return

    // Remove old image and upload new one
    images.value.splice(index, 1)
    uploadFile(file)
  }
  input.click()
}

// Open material library
function openMaterialLibrary(index: number) {
  emit('open-material-library', index)
}

// Set image from material library (called by parent)
function setImageFromLibrary(index: number, imageData: Partial<UploadImageItem>) {
  if (index >= 0 && index < images.value.length) {
    images.value[index] = { ...images.value[index], ...imageData } as UploadImageItem
  } else if (images.value.length < props.maxCount) {
    images.value.push({
      id: `img-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      ...imageData,
      uploading: false,
      progress: 100,
    } as UploadImageItem)
  }
}

// Drag and drop handlers
function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false

  const files = Array.from(e.dataTransfer?.files || [])
  const imageFiles = files.filter(f => f.type.startsWith('image/'))

  if (!imageFiles.length) {
    ElMessage.warning('请拖入图片文件')
    return
  }

  const remainingSlots = props.maxCount - images.value.length
  const filesToUpload = imageFiles.slice(0, remainingSlots)

  if (imageFiles.length > remainingSlots) {
    ElMessage.warning(`最多只能上传 ${props.maxCount} 张图片，已自动截取前 ${remainingSlots} 张`)
  }

  filesToUpload.forEach(file => uploadFile(file))
}


// Expose methods for parent
defineExpose({
  setImageFromLibrary,
  triggerUpload,
})
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.image-uploader {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

// ===== Header =====
.uploader-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.uploader-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
}

.title-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: $gradient-brand;
}

.uploader-count {
  font-size: 12px;
  color: $text-muted;
  background: rgba($overlay-rgb, 0.06);
  padding: 4px 10px;
  border-radius: 12px;
}

// ===== Image Grid =====
.image-grid {
  display: grid;
  grid-template-columns: repeat(v-bind(columns), 1fr);
  gap: 12px;
  max-height: calc(v-bind(visibleRows) * 200px + (v-bind(visibleRows) - 1) * 12px);
  overflow-y: auto;
  padding: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba($overlay-rgb, 0.1) transparent;

  &::-webkit-scrollbar {
    width: 4px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba($overlay-rgb, 0.1);
    border-radius: 2px;
  }
  &::-webkit-scrollbar-track {
    background: transparent;
  }
}

// ===== Image Item =====

// ===== Uploading Overlay =====

// ===== Hover Overlay =====

// ===== Sort Handle =====

// ===== Index Badge =====

// ===== Upload Trigger =====
.upload-trigger-wrapper {
  display: flex;
  flex-direction: column;
}

.upload-trigger {
  aspect-ratio: 3 / 4;
  border: 2px dashed rgba($overlay-rgb, 0.1);
  border-radius: $radius-sm;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: rgba($overlay-rgb, 0.02);
  color: $text-muted;

  &:hover {
    border-color: $brand-start;
    color: $brand-start;
    background: rgba($brand-start, 0.04);
    box-shadow: 0 0 20px rgba($brand-start, 0.08);
  }

  &.drag-over {
    border-color: $brand-start;
    background: rgba($brand-start, 0.08);
    border-style: solid;
    box-shadow: 0 0 24px rgba($brand-start, 0.15);

    .el-icon {
      color: $brand-start;
      transform: scale(1.2);
    }
  }

  .el-icon {
    transition: transform 0.3s ease;
  }

  .upload-text {
    font-size: 13px;
    font-weight: 600;
  }

  .upload-hint {
    font-size: 11px;
    color: $text-placeholder;
  }
}

.upload-placeholder-name {
  margin-top: 6px;
  height: 16px; // 与 .image-name 高度一致
}

// ===== SortableJS Ghost =====
.sortable-ghost {
  opacity: 0.4;
  border: 2px dashed $brand-start !important;
}

.sortable-chosen {
  box-shadow: 0 0 0 2px $brand-start;
}

.sortable-drag {
  transform: scale(1.05);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
}
</style>
