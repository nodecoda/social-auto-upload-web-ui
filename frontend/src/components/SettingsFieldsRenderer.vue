<template>
            <template v-for="field in fields" :key="field.key">
              <template v-if="field.key !== 'title' && field.key !== 'description' && field.key !== 'videoFormat'">
                <div
                  v-if="!field.visibleWhen || form[field.visibleWhen.key] === field.visibleWhen.value"
                  :class="['setting-card', { 'setting-card--full-row': field.fullRow }]"
                  :style="{ borderColor: platform.color + '26', background: platform.color + '0a' }"
                >
                  <div class="setting-label" :style="{ color: platform.color }">
                    <span v-if="field.required" style="color: #f56c6c; margin-right: 2px;">*</span>
                    {{ field.label }}
                  </div>
                  <div v-if="field.description" class="setting-desc">{{ field.description }}</div>

                  <el-input
                    v-if="field.type === 'input'"
                    v-model="form[field.key]"
                    :placeholder="field.placeholder"
                    size="small"
                  />
                  <el-switch
                    v-else-if="field.type === 'switch'"
                    v-model="form[field.key]"
                  />
                  <div v-else-if="field.type === 'radio'" class="radio-row" :class="{ 'is-disabled': field.disabledWhen && form[field.disabledWhen.key] === field.disabledWhen.value }">
                    <label
                      v-for="opt in field.options"
                      :key="String(opt.value)"
                      :class="['radio-item', { 'cursor-pointer': !(field.disabledWhen && form[field.disabledWhen.key] === field.disabledWhen.value), 'is-disabled': field.disabledWhen && form[field.disabledWhen.key] === field.disabledWhen.value }]"
                    >
                      <input
                        type="radio"
                        :name="(selectedAccountId || selectedPlatform) + '-' + field.key"
                        :value="opt.value"
                        v-model="form[field.key]"
                        :disabled="field.disabledWhen && form[field.disabledWhen.key] === field.disabledWhen.value"
                        class="cursor-pointer"
                      />
                      <span
                        :class="['radio-text', { on: form[field.key] === opt.value }]"
                        :style="form[field.key] === opt.value && !(field.disabledWhen && form[field.disabledWhen.key] === field.disabledWhen.value) ? { borderColor: platform.color, color: platform.color } : {}"
                      >{{ opt.label }}</span>
                    </label>
                  </div>
                  <el-select
                    v-else-if="field.type === 'select'"
                    v-model="form[field.key]"
                    :placeholder="field.placeholder"
                    size="small"
                    clearable
                    class="cursor-pointer"
                  >
                    <el-option
                      v-for="opt in (field.options || [])"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                    />
                    <el-option v-if="!field.options || field.options.length === 0" label="暂无可选项" :value="''" disabled />
                  </el-select>
                  <el-select
                    v-else-if="field.type === 'multiSelect'"
                    v-model="form[field.key]"
                    :placeholder="field.placeholder"
                    size="small"
                    multiple
                    collapse-tags
                    collapse-tags-tooltip
                    clearable
                    class="cursor-pointer"
                  >
                    <el-option
                      v-for="opt in (field.options || [])"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                    />
                    <el-option v-if="!field.options || field.options.length === 0" label="暂无可选项" :value="''" disabled />
                  </el-select>
                  <el-date-picker
                    v-else-if="field.type === 'datetime'"
                    v-model="form[field.key]"
                    type="datetime"
                    :placeholder="field.placeholder"
                    :disabled-date="field.disabledDate || (field.key === 'scheduleTime' ? scheduleDisabledDate : undefined)"
                    :disabled-hours="field.disabledHours || (field.key === 'scheduleTime' ? () => scheduleDisabledHours(field.key) : undefined)"
                    :disabled-minutes="field.disabledMinutes || (field.key === 'scheduleTime' ? (h: number) => scheduleDisabledMinutes(field.key, h) : undefined)"
                    value-format="YYYY-MM-DD HH:mm:ss"
                    size="small"
                    class="cursor-pointer"
                  />
                  <el-date-picker
                    v-else-if="field.type === 'date'"
                    v-model="form[field.key]"
                    type="date"
                    :placeholder="field.placeholder"
                    :disabled-date="(date: Date) => date > new Date()"
                    value-format="YYYY-MM-DD"
                    size="small"
                    class="cursor-pointer"
                  />
                  <XhsPoiSelect
                    v-else-if="field.type === 'poiSelect' && !field.key.startsWith('vivo')"
                    :account-id="selectedAccountId"
                    v-model="form[field.key]"
                    :data="form[field.key + 'Data']"
                    @change="(val) => handleXhsPoiChange(field.key, val)"
                  />
                  <VivoPositionSelect
                    v-else-if="field.type === 'poiSelect' && field.key.startsWith('vivo')"
                    :account-id="selectedAccountId"
                    v-model="form[field.key]"
                    :data="form[field.key + 'Data']"
                    @change="(val) => handleXhsPoiChange(field.key, val)"
                  />
                  <el-cascader
                    v-else-if="field.type === 'cascader'"
                    v-model="form[field.key]"
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
                    v-model="form[field.key]"
                    :data="form.compilationData"
                    :fetcher="fetchCompilation"
                    :field-map="compilationFieldMap"
                    search-mode="backend"
                    empty-behavior="clear"
                    placeholder="输入合集名称搜索"
                    search-placeholder="输入合集名称,按回车搜索"
                    @change="(val) => handleAlipayCompilationChange(field.key, val)"
                  />
                </div>
              </template>
            </template>
</template>

<script setup lang="ts">
import { type PropType } from 'vue'
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
  options?: any[]
  visibleWhen?: { key: string; value: string | number | boolean }
  disabledWhen?: { key: string; value: string | number | boolean }
  disabledDate?: (date: Date) => boolean
  disabledHours?: (row: Date) => number[]
  disabledMinutes?: (row: Date, hour: number) => number[]
  props?: Record<string, any>
  [key: string]: any
}

const props = defineProps({
  // 平台配置 settingsFields 字段数组
  fields: { type: Array as PropType<SettingsField[]>, default: (): any[] => [] },
  // 发布表单（本组件直接读写其中的字段）
  form: { type: Object as PropType<Record<string, any>>, required: true },
  // 当前平台配置（color/key/hideFields 等）
  platform: { type: Object as PropType<Record<string, any> | null>, default: null },
  selectedPlatform: { type: String, default: null },
  selectedAccountId: { type: [String, Number] as PropType<string | number | null>, default: null },
})

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

function _sameDay(a: any, b: any) {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate()
}

// disabled-hours: 选中日期为今天时禁用已过去的小时
function scheduleDisabledHours(fieldKey: string) {
  if (fieldKey !== 'scheduleTime') return []
  const raw = props.form[fieldKey]
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
  const raw = props.form[fieldKey]
  if (!raw) return []
  const selected = new Date(raw)
  if (isNaN(selected.getTime())) return []
  const now = new Date()
  if (!_sameDay(selected, now) || hour !== now.getHours()) return []
  return Array.from({ length: now.getMinutes() }, (_, i) => i)
}

// ----- 小红书拍摄地点(POI)选择回调:存完整对象到 <key>Data,publishData 取 poi 名称 -----
function handleXhsPoiChange(fieldKey: string, poi: Record<string, any> | null) {
  if (poi) {
    props.form[fieldKey + 'Data'] = poi
  } else {
    props.form[fieldKey + 'Data'] = null
  }
}

// ----- 支付宝/头条合集(compilation)回调:存完整对象便于回显 -----
function handleAlipayCompilationChange(fieldKey: string, comp: Record<string, any> | null) {
  if (comp) {
    props.form.compilationData = comp
  } else {
    props.form.compilationData = null
  }
}

// ----- 支付宝/头条合集(compilation) RemoteSearchSelect 数据源(后端搜索模式) -----
// 按 selectedPlatform 切换 api:头条用 toutiaoApi,其余用 alipayApi
async function fetchCompilation(keyword?: string) {
  const api = props.selectedPlatform === 'toutiao' ? toutiaoApi : alipayApi
  const resp = (await api.searchCompilation(props.selectedAccountId, keyword || '')) as ApiResponse<{ list?: any[] }>
  return { list: resp.data?.list || [] }
}

// compilation 字段映射:title 主标题,category+total 派生描述,coverUrl 扁平封面
const compilationFieldMap = {
  label: 'title',
  key: 'compilationId',
  desc: (item: any) => {
    const parts = []
    if (item.category) parts.push(item.category)
    if (item.total != null) parts.push(`${item.total} 个内容`)
    return parts.join(' · ')
  },
  cover: 'coverUrl'
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
@use '@/styles/settings-card.scss' as *;

.cursor-pointer {
  cursor: pointer;
}
</style>
