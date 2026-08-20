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

                  <SettingFieldControl
                    v-model="form[field.key]"
                    :field="field"
                    :form="form"
                    :platform-color="platform.color"
                    :selected-account-id="selectedAccountId"
                    :selected-platform="selectedPlatform"
                    @poi-change="handleXhsPoiChange"
                    @compilation-change="handleAlipayCompilationChange"
                  />
                </div>
              </template>
            </template>

</template>
<script setup lang="ts">
import { type PropType } from 'vue'
import SettingFieldControl from '@/components/SettingFieldControl.vue'

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
  disabledDate?: (...args: any[]) => boolean
  disabledHours?: (...args: any[]) => number[]
  disabledMinutes?: (...args: any[]) => number[]
  props?: Record<string, any>
  [key: string]: any
}

const props = defineProps({
  // 平台配置 settingsFields 字段数组
  fields: { type: Array as PropType<SettingsField[]>, default: (): any[] => [] },
  // 发布表单（本组件直接读写其中的字段）
  form: { type: Object as PropType<Record<string, any>>, required: true },
  // 当前平台配置（color/key/hideFields 等）
  platform: { type: Object as PropType<Record<string, any>>, default: () => ({}) },
  selectedPlatform: { type: String, default: null },
  selectedAccountId: { type: [String, Number] as PropType<string | number | null>, default: null },
})

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

</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
@use '@/styles/settings-card.scss' as *;

.cursor-pointer {
  cursor: pointer;
}
</style>
