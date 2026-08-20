<template>
  <div class="activity-select">
    <el-select
      v-model="selectedActivities"
      placeholder="选择官方活动（最多5个）"
      clearable
      filterable
      multiple
      multiple-limit="5"
      no-data-text=" "
      @change="handleChange"
      style="width: 100%"
    >
      <template #header>
        <div v-if="loading" class="loading-indicator">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>加载中...</span>
        </div>
      </template>
      <el-option
        v-for="activity in activityList"
        :key="activity.activity_id"
        :label="activity.activity_name"
        :value="activity.activity_name"
      >
        <div class="activity-option">
          <img
            v-if="activity.cover_image"
            :src="activity.cover_image"
            class="activity-cover"
            @error="onImageError"
          />
          <div v-else class="activity-cover-placeholder">
            <el-icon><Promotion /></el-icon>
          </div>
          <div class="activity-info">
            <div class="activity-name">{{ activity.activity_name }}</div>
            <div class="activity-meta">
              <span class="activity-hot">热度：{{ activity.hot_score || 0 }}</span>
              <span v-if="activity.show_end_time" class="activity-time">
                截止：{{ activity.show_end_time }}
              </span>
            </div>
          </div>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Loading, Promotion } from '@element-plus/icons-vue'
import { douyinImageApi } from '@/api/douyinImage'
import { type ApiResponse } from '@/utils/request'

const props = withDefaults(defineProps<{
  accountId?: string | number | null
  // v-model 存已选活动名数组(发布时按名称匹配 activity_id)
  modelValue?: string[]
}>(), {
  accountId: '',
  modelValue: () => [],
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void
  (e: 'change', payload: ActivityItem[]): void
}>()

interface ActivityItem {
  activity_id: string | number
  activity_name: string
  cover_image?: string
  hot_score?: number
  show_end_time?: string
  [key: string]: unknown
}

const loading = ref(false)
const activityList = ref<ActivityItem[]>([])
const selectedActivities = ref<string[]>(props.modelValue || [])

watch(() => props.modelValue, (val) => {
  selectedActivities.value = val || []
})

onMounted(() => {
  if (props.accountId) {
    loadActivityList()
  }
})

watch(() => props.accountId, (val) => {
  if (val) {
    loadActivityList()
  }
})

async function loadActivityList() {
  loading.value = true
  try {
    const resp = (await douyinImageApi.getActivityList(props.accountId || '')) as ApiResponse<{ activity_list?: ActivityItem[] }>
    if (resp.code === 200) {
      activityList.value = (resp.data?.activity_list || []) as ActivityItem[]
    }
  } catch (e) {
    console.error('加载活动列表失败:', e)
  } finally {
    loading.value = false
  }
}

function handleChange(val: string[]) {
  emit('update:modelValue', val)
  const activities = activityList.value.filter(a => val.includes(a.activity_name))
  emit('change', activities)
}

function onImageError(e: Event) {
  ;(e.target as HTMLImageElement).src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjZjVmNWY1Ii8+PHRleHQgeD0iMjAiIHk9IjI0IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPuKcqOW+izwvdGV4dD48L3N2Zz4=';
}
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.activity-select {
  width: 100%;
}

.search-input-wrapper {
  padding: 8px 12px;
}

.loading-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 12px;
  color: $text-secondary;
  font-size: 13px;

  .is-loading {
    animation: rotating 1s linear infinite;
  }

  @keyframes rotating {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
}

.activity-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.activity-cover {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
}

.activity-cover-placeholder {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  background: $popper-hover;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #F97316;
  flex-shrink: 0;
}

.activity-info {
  flex: 1;
  min-width: 0;
}

.activity-name {
  font-size: 14px;
  color: $popper-text;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: $text-secondary;
}

.activity-hot {
  color: #EF4444;
}
</style>
