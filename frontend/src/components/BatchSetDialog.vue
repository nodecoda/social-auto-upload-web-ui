<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    :title="title"
    width="720px"
    top="8vh"
    :close-on-click-modal="false"
  >
    <el-form label-position="top">
      <el-form-item label="标题">
        <el-input
          v-model="formTitle"
          maxlength="100"
          show-word-limit
          placeholder="留空表示清空原值"
          clearable
        />
      </el-form-item>
      <el-form-item label="描述">
        <el-input
          v-model="formDescription"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="留空表示清空原值"
        />
      </el-form-item>
      <el-form-item label="标签">
        <div class="tag-input-wrap">
          <el-input
            v-model="tagInput"
            placeholder="输入标签内容，按回车添加"
            @keyup.enter="addTag"
            clearable
          />
          <div v-if="formTags.length > 0" class="tags-list">
            <el-tag
              v-for="(tag, index) in formTags"
              :key="index"
              closable
              @close="removeTag(index)"
              size="small"
            >#{{ tag }}</el-tag>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="定时发布">
        <el-date-picker
          v-model="formScheduleTime"
          type="datetime"
          placeholder="留空表示立即发布，选择时间则定时发布"
          format="YYYY-MM-DD HH:mm:ss"
          value-format="YYYY-MM-DD HH:mm:ss"
          clearable
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="渠道">
        <BatchChannelPicker
          :platforms="platforms"
          :checked-keys="checkedKeys"
          @toggle="toggleKey"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        plain
        :disabled="checkedCount === 0"
        @click="handleApply('partial')"
      >
        仅应用已填写
      </el-button>
      <el-button
        type="primary"
        :disabled="checkedCount === 0"
        @click="handleApply('full')"
      >
        全量应用
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, type PropType } from 'vue'
import { ElMessage } from 'element-plus'
import BatchChannelPicker from '@/components/BatchChannelPicker.vue'

const MAX_TAGS = 10

interface PlatformOption {
  key: string
  name: string
  logo?: string
  count: number
}

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  platforms: { type: Array as PropType<PlatformOption[]>, required: true },
  title: { type: String, default: '批量设置' },
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'apply', payload: string[], options: { title: string; description: string; tags: string[]; scheduleTime: string; mode: 'full' | 'partial' }): void
}>()

const formTitle = ref('')
const formDescription = ref('')
const formTags = ref<string[]>([])
const tagInput = ref('')
const formScheduleTime = ref('')
const checkedKeys = ref(new Set<string>())

const checkedCount = computed(() => checkedKeys.value.size)

watch(() => props.modelValue, (open) => {
  if (open) {
    formTitle.value = ''
    formDescription.value = ''
    formTags.value = []
    tagInput.value = ''
    formScheduleTime.value = ''
    checkedKeys.value = new Set(
      props.platforms.filter(p => p.count > 0).map(p => p.key)
    )
  }
})

function toggleKey(p: PlatformOption) {
  if (p.count === 0) return
  const next = new Set(checkedKeys.value)
  if (next.has(p.key)) {
    next.delete(p.key)
  } else {
    next.add(p.key)
  }
  checkedKeys.value = next
}

function addTag() {
  const v = (tagInput.value || '').trim()
  if (!v) return
  if (formTags.value.length >= MAX_TAGS) {
    ElMessage.warning(`最多 ${MAX_TAGS} 个标签`)
    return
  }
  if (formTags.value.includes(v)) {
    tagInput.value = ''
    return
  }
  formTags.value = [...formTags.value, v]
  tagInput.value = ''
}

function removeTag(idx: number) {
  formTags.value = formTags.value.filter((_, i) => i !== idx)
}

function handleApply(mode: 'full' | 'partial' = 'full') {
  emit('apply', Array.from(checkedKeys.value), {
    title: formTitle.value,
    description: formDescription.value,
    tags: [...formTags.value],
    scheduleTime: formScheduleTime.value || '',
    // 'full' = 全量覆盖（空值也会清空原值）；'partial' = 仅覆盖已填写字段（空值跳过）
    mode,
  })
  emit('update:modelValue', false)
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.tag-input-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
