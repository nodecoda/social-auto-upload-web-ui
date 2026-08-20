<template>
  <RemoteSearchSelect
    :model-value="modelValue"
    :data="data"
    :fetcher="fetchPoi"
    :field-map="poiFieldMap"
    search-mode="backend"
    empty-behavior="block"
    placeholder="搜索拍摄地点"
    search-placeholder="输入地点关键词,按回车搜索"
    @update:model-value="(val) => $emit('update:modelValue', val)"
    @change="$emit('change', $event)"
  />
</template>

<script setup lang="ts">
import { type ApiResponse } from '@/utils/request'
import { xhsApi } from '@/api/xiaohongshu'
import RemoteSearchSelect from '@/components/common/RemoteSearchSelect.vue'

const props = withDefaults(defineProps<{
  // POI 搜索需账号 cookie,透传 selectedAccountId
  accountId?: string | number | null
  // v-model 存地点名称
  modelValue?: string
  // 回显用的完整对象(含 poi_id)
  data?: PoiItem | null
}>(), {
  accountId: '',
  modelValue: '',
  data: null,
})

defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'change', payload: PoiItem | null): void
}>()

// 走全局公共组件 RemoteSearchSelect:后端搜索模式(必须传 keyword,空关键词不请求)。
// 与视频号位置 fetchChannelsLocations 保持一致风格。
interface PoiItem {
  poi_id?: string | number
  name?: string
  full_address?: string
  address?: string
  [key: string]: unknown
}

async function fetchPoi(keyword: string) {
  const resp = (await xhsApi.searchPoi(props.accountId, keyword || '')) as ApiResponse<{ poi_list?: PoiItem[] }>
  return { list: resp.data?.poi_list || [] }
}

// 字段映射:name 作 label,full_address || address 作 desc 副文案,poi_id 作 key
const poiFieldMap: Record<string, string | ((item: PoiItem) => string)> = {
  key: 'poi_id',
  label: 'name',
  desc: (item: PoiItem) => item.full_address || item.address || ''
}
</script>