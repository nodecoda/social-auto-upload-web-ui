<template>
  <el-input
    v-if="field.type === 'input'"
    v-model="value"
    :placeholder="field.placeholder"
    size="small"
  />
  <el-switch
    v-else-if="field.type === 'switch'"
    v-model="value"
  />
  <div v-else-if="field.type === 'radio'" class="radio-row" :class="{ 'is-disabled': isRadioDisabled }">
    <label
      v-for="opt in field.options"
      :key="String(opt.value)"
      :class="['radio-item', { 'cursor-pointer': !isRadioDisabled, 'is-disabled': isRadioDisabled }]"
    >
      <input
        type="radio"
        :name="radioName"
        :value="opt.value"
        v-model="value"
        :disabled="isRadioDisabled"
        class="cursor-pointer"
      />
      <span
        :class="['radio-text', { on: value === opt.value }]"
        :style="radioTextStyle(opt)"
      >{{ opt.label }}</span>
    </label>
  </div>
  <el-select
    v-else-if="field.type === 'select' || field.type === 'multiSelect'"
    v-model="value"
    :placeholder="field.placeholder"
    size="small"
    :multiple="field.type === 'multiSelect'"
    :collapse-tags="field.type === 'multiSelect'"
    :collapse-tags-tooltip="field.type === 'multiSelect'"
    clearable
    class="cursor-pointer"
  >
    <el-option v-for="opt in (field.options || [])" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
    <el-option v-if="!field.options || field.options.length === 0" label="暂无可选项" :value="''" disabled />
  </el-select>
  <el-date-picker
    v-else-if="field.type === 'datetime' || field.type === 'date'"
    v-model="value"
    :type="field.type"
    :placeholder="field.placeholder"
    :disabled-date="pickerDisabledDate"
    :disabled-hours="pickerDisabledHours"
    :disabled-minutes="pickerDisabledMinutes"
    :value-format="pickerValueFormat"
    size="small"
    class="cursor-pointer"
  />
  <XhsPoiSelect
    v-else-if="field.type === 'poiSelect' && !field.key.startsWith('vivo')"
    :account-id="selectedAccountId"
    v-model="value"
    :data="(form[field.key + 'Data'] as PoiSelectData | null)"
    @change="(val) => emit('poi-change', field.key, val)"
  />
  <VivoPositionSelect
    v-else-if="field.type === 'poiSelect' && field.key.startsWith('vivo')"
    :account-id="selectedAccountId"
    v-model="value"
    :data="(form[field.key + 'Data'] as PoiSelectData | null)"
    @change="(val) => emit('poi-change', field.key, val)"
  />
  <el-cascader
    v-else-if="field.type === 'cascader'"
    v-model="value"
    :options="field.options || []"
    :placeholder="field.placeholder"
    :props="field.props || { expandTrigger: 'hover' }"
    size="small"
    clearable
    filterable
    class="cursor-pointer weibo-cascader"
  />
  <RemoteSearchSelect
    v-else-if="field.type === 'compilationSelect'"
    v-model="value"
    :data="(form.compilationData as Record<string, unknown> | null)"
    :fetcher="fetchCompilation"
    :field-map="compilationFieldMap"
    search-mode="backend"
    empty-behavior="clear"
    placeholder="输入合集名称搜索"
    search-placeholder="输入合集名称,按回车搜索"
    @change="(val) => emit('compilation-change', field.key, val)"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { type ApiResponse } from '@/utils/request'
import XhsPoiSelect from '@/components/xiaohongshu/PoiSelect.vue'
import VivoPositionSelect from '@/components/vivo/PositionSelect.vue'
import RemoteSearchSelect from '@/components/common/RemoteSearchSelect.vue'
import { alipayApi } from '@/api/alipay'
import { toutiaoApi } from '@/api/toutiao'

// 平台 settingsFields 字段项(部分字段仅特定 type 使用;其余字段透传)
interface SettingsField {
  key: string
  label?: string
  type?: string
  required?: boolean
  description?: string
  placeholder?: string
  fullRow?: boolean
  options?: Array<{ label: string; value: string | boolean }>
  visibleWhen?: { key: string; value: string | number | boolean }
  disabledWhen?: { key: string; value: string | number | boolean }
  disabledDate?: (date: Date) => boolean
  disabledHours?: (role: string, comparingDate?: Date | { toDate: () => Date } | null) => number[]
  disabledMinutes?: (hour: number, role: string, comparingDate?: Date | { toDate: () => Date } | null) => number[]
  props?: Record<string, unknown>
  [key: string]: unknown
}

// PoiSelect data prop 形状(PoiSelect.PoiItem 未导出,按结构声明用于动态表单数据收窄)
interface PoiSelectData {
  poi_id?: string | number
  name?: string
  full_address?: string
  address?: string
  [key: string]: unknown
}

const props = defineProps<{
  // 字段配置
  field: SettingsField
  // 字段当前值 (v-model = form[field.key])
  // 按 field.type 变化:字符串/布尔/数字/数组等多形态,故保持 any 作为多态边界
  modelValue: any
  // 完整发布表单:用于 disabledWhen 联动 / poi Data / compilationData
  form: Record<string, unknown>
  platformColor: string
  selectedAccountId: string | number | null
  selectedPlatform: string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: unknown): void
  (e: 'poi-change', key: string, poi: Record<string, unknown> | null): void
  (e: 'compilation-change', key: string, comp: Record<string, unknown> | null): void
}>()

const value = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

// ----- radio: 禁用联动 + 样式 -----
const isRadioDisabled = computed(() => {
  const d = props.field.disabledWhen
  return !!(d && props.form[d.key] === d.value)
})

const radioName = computed(() => `${props.selectedAccountId || props.selectedPlatform || ''}-${props.field.key}`)

function radioTextStyle(opt: { label: string; value: string | boolean }) {
  const active = props.modelValue === opt.value && !isRadioDisabled.value
  return active ? { borderColor: props.platformColor, color: props.platformColor } : {}
}

// ----- 定时发布禁用逻辑（仅 scheduleTime 生效）-----
// 定时发布:必须晚于当前时间,最多往后 14 天
// 仅对 scheduleTime 字段生效,其它 datetime 字段不受影响
const SCHEDULE_MAX_DAYS = 14

function scheduleDisabledDate(date: Date) {
  if (!date) return false
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const maxDate = new Date(startOfToday)
  maxDate.setDate(maxDate.getDate() + SCHEDULE_MAX_DAYS)
  return date < startOfToday || date > maxDate
}

function _sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate()
}

// disabled-hours: 选中日期为今天时禁用已过去的小时
function scheduleDisabledHours(fieldKey: string) {
  if (fieldKey !== 'scheduleTime') return []
  const raw = props.modelValue
  if (!raw) return []
  const selected = new Date(raw)
  if (isNaN(selected.getTime())) return []
  const now = new Date()
  if (!_sameDay(selected, now)) return []
  return Array.from({ length: now.getHours() }, (_, i) => i)
}

// disabled-minutes: 选中日期为今天且小时为当前小时时禁用已过去的分钟
function scheduleDisabledMinutes(fieldKey: string, hour: number) {
  if (fieldKey !== 'scheduleTime') return []
  const raw = props.modelValue
  if (!raw) return []
  const selected = new Date(raw)
  if (isNaN(selected.getTime())) return []
  const now = new Date()
  if (!_sameDay(selected, now) || hour !== now.getHours()) return []
  return Array.from({ length: now.getMinutes() }, (_, i) => i)
}

// ----- 日期/时间选择器禁用与格式（datetime 走 scheduleTime 特殊逻辑, date 仅禁用未来）-----
const pickerDisabledDate = computed(() => {
  if (props.field.type === 'date') return (date: Date) => date > new Date()
  return props.field.disabledDate || (props.field.key === 'scheduleTime' ? scheduleDisabledDate : undefined)
})
const pickerDisabledHours = computed(() => {
  if (props.field.type !== 'datetime') return undefined
  return props.field.disabledHours || (props.field.key === 'scheduleTime' ? () => scheduleDisabledHours(props.field.key) : undefined)
})
const pickerDisabledMinutes = computed(() => {
  if (props.field.type !== 'datetime') return undefined
  return props.field.disabledMinutes || (props.field.key === 'scheduleTime' ? (h: number) => scheduleDisabledMinutes(props.field.key, h) : undefined)
})
const pickerValueFormat = computed(() => props.field.type === 'datetime' ? 'YYYY-MM-DD HH:mm:ss' : 'YYYY-MM-DD')

// ----- 支付宝/头条合集(compilation) RemoteSearchSelect 数据源(后端搜索模式) -----
// 按 selectedPlatform 切换 api:头条用 toutiaoApi,其余用 alipayApi
interface CompilationItem {
  compilationId?: string | number
  title: string
  coverUrl?: string
  category?: string
  total?: number
  [key: string]: unknown
}

async function fetchCompilation(keyword?: string) {
  const api = props.selectedPlatform === 'toutiao' ? toutiaoApi : alipayApi
  const resp = (await api.searchCompilation(props.selectedAccountId, keyword || '')) as ApiResponse<{ list?: CompilationItem[] }>
  return { list: resp.data?.list || [] }
}

// compilation 字段映射:title 主标题,category+total 派生描述,coverUrl 扁平封面
const compilationFieldMap = {
  label: 'title',
  key: 'compilationId',
  desc: (item: Record<string, unknown>) => {
    const c = item as CompilationItem
    const parts = []
    if (c.category) parts.push(c.category)
    if (c.total != null) parts.push(`${c.total} 个内容`)
    return parts.join(' · ')
  },
  cover: 'coverUrl'
}
</script>
