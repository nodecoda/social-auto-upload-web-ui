/**
 * 共享测试桩 (shared stubs)
 *
 * 仅被 *.test.js 通过 import 使用,自身不直接运行
 * (vitest include 只覆盖 src/**\/*.test.js,本文件不会被当作测试收集)。
 *
 * 用途:在 jsdom 下替换 element-plus 组件,规避 teleport / 全局插件依赖,
 * 让组件测试聚焦渲染与交互断言。
 */
import { vi } from 'vitest'

/** ElButton:透传 disabled,点击发出 click */
export const ElButton = {
  name: 'ElButton',
  props: ['disabled'],
  emits: ['click'],
  template: '<button :disabled="disabled" class="el-button-stub" @click="$emit(\'click\')"><slot /></button>',
}

/** ElDialog:规避 teleport 到 body;监听 modelValue(visible),渲染默认插槽 + footer */
export const ElDialog = {
  name: 'ElDialog',
  props: ['modelValue', 'title', 'width', 'top', 'closeOnClickModal'],
  emits: ['update:modelValue'],
  template: `
    <div v-if="modelValue" class="el-dialog-stub">
      <div class="el-dialog-stub-title">{{ title }}</div>
      <slot />
      <slot name="footer" />
    </div>
  `,
}

/** ElMessage:可断言的全局消息 mock */
export const ElMessage = {
  warning: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}

/** ElIcon:图标容器(子组件 @element-plus/icons-vue 直接渲染,无需 mock) */
export const ElIcon = {
  name: 'ElIcon',
  template: '<i class="el-icon-stub"><slot /></i>',
}

/** ElTooltip:透传插槽 */
export const ElTooltip = {
  name: 'ElTooltip',
  props: ['content', 'placement', 'disabled'],
  template: '<div class="el-tooltip-stub"><slot /></div>',
}

/** ElEmpty:渲染 description 文案 */
export const ElEmpty = {
  name: 'ElEmpty',
  props: ['description'],
  template: '<div class="el-empty-stub">{{ description }}</div>',
}

/** ElPagination:渲染 total,提供翻页交互以触发 current-change */
export const ElPagination = {
  name: 'ElPagination',
  props: ['total', 'currentPage', 'pageSize', 'pageSizes', 'layout'],
  emits: ['update:currentPage', 'update:pageSize', 'current-change', 'size-change'],
  template: `
    <div class="el-pagination-stub">
      <span class="pagination-total">共 {{ total }} 条</span>
      <button class="pagination-next" @click="$emit('update:currentPage', (currentPage || 0) + 1); $emit('current-change', (currentPage || 0) + 1)">下一页</button>
    </div>
  `,
}

/** ElForm:容器 */
export const ElForm = {
  name: 'ElForm',
  template: '<div class="el-form-stub"><slot /></div>',
}

/** ElFormItem:渲染 label + 插槽,便于断言字段标签 */
export const ElFormItem = {
  name: 'ElFormItem',
  props: ['label'],
  template: '<div class="el-form-item-stub"><span class="el-form-item-label">{{ label }}</span><slot /></div>',
}

/** ElInput:支持 v-model,透传 keyup 以便测试回车添加标签 */
export const ElInput = {
  name: 'ElInput',
  props: ['modelValue', 'type', 'placeholder', 'maxlength', 'rows', 'clearable', 'showWordLimit'],
  emits: ['update:modelValue', 'keyup', 'keydown', 'input'],
  template: `
    <input
      class="el-input-stub"
      :value="modelValue"
      :type="type === 'textarea' ? 'text' : (type || 'text')"
      :placeholder="placeholder"
      @input="$emit('update:modelValue', $event.target.value)"
      @keyup="$emit('keyup', $event)"
    />
  `,
}

/** ElTag:渲染 # 前缀文本,close 点击发出 close */
export const ElTag = {
  name: 'ElTag',
  props: ['closable', 'size'],
  emits: ['close'],
  template: '<span class="el-tag-stub" @click="$emit(\'close\')"><slot /></span>',
}

/** ElDatePicker:支持 v-model 的简单输入框 */
export const ElDatePicker = {
  name: 'ElDatePicker',
  props: ['modelValue', 'type', 'placeholder', 'format', 'valueFormat', 'clearable'],
  emits: ['update:modelValue'],
  template: `
    <input
      class="el-date-picker-stub"
      :value="modelValue"
      :placeholder="placeholder"
      @input="$emit('update:modelValue', $event.target.value)"
    />
  `,
}

/** 常见 el-dialog 依赖合集:直接展开到 global.stubs 使用 */
export const elementDialogStubs = {
  ElButton,
  ElDialog,
  ElIcon,
  ElTooltip,
  ElEmpty,
  ElPagination,
  ElForm,
  ElFormItem,
  ElInput,
  ElTag,
  ElDatePicker,
}

/** ElSwitch:可点击的布尔开关,v-model 点击翻转 */
export const ElSwitch = {
  name: 'ElSwitch',
  props: ['modelValue', 'disabled'],
  emits: ['update:modelValue'],
  template: '<button class="el-switch-stub" type="button" :disabled="disabled" @click="$emit(\'update:modelValue\', !modelValue)"><slot /></button>',
}

/** ElInputNumber:数字输入框 */
export const ElInputNumber = {
  name: 'ElInputNumber',
  props: ['modelValue', 'min', 'max'],
  emits: ['update:modelValue'],
  template: '<input class="el-input-number-stub" type="number" :value="modelValue" @input="$emit(\'update:modelValue\', Number($event.target.value))" />',
}

/** ElSelect:透传插槽渲染选项 */
export const ElSelect = {
  name: 'ElSelect',
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<div class="el-select-stub"><slot /></div>',
}

/** ElOption:选项行,点击发出 select 选择 */
export const ElOption = {
  name: 'ElOption',
  props: ['label', 'value'],
  emits: ['select'],
  template: '<span class="el-option-stub" @click="$emit(\'select\', value)">{{ label }}</span>',
}

/** ElCollapse:折叠容器 */
export const ElCollapse = {
  name: 'ElCollapse',
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<div class="el-collapse-stub"><slot /></div>',
}

/** ElCollapseItem:折叠项,渲染标题 + 默认插槽 */
export const ElCollapseItem = {
  name: 'ElCollapseItem',
  props: ['title', 'name'],
  template: '<div class="el-collapse-item-stub"><span class="el-collapse-item-title">{{ title }}</span><slot /></div>',
}
