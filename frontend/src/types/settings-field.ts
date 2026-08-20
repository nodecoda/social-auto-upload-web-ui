/**
 * 平台 settingsFields 字段类型（判别联合）
 *
 * SettingFieldControl / SettingsFieldsRenderer / PublishCenter / config/platforms.ts
 * 共用此类型:按 `field.type` 字面量判别,模板与脚本内可对 options/props/placeholder
 * 等字段做精确收窄。字段值类型随控件变化,见 SettingsFieldValue。
 *
 * 注意:各变体保留索引签名透传平台配置的未声明键(如 toutiao extendLink 的 linkField),
 * 因此配置字面量不受多余属性检查约束,但已声明字段在收窄后类型精确。
 */

/** 字段渲染控件类型全集 */
export type SettingsFieldType =
  | 'input'
  | 'switch'
  | 'radio'
  | 'select'
  | 'multiSelect'
  | 'datetime'
  | 'date'
  | 'poiSelect'
  | 'cascader'
  | 'compilationSelect'

/** 字段当前值（随 field.type 变化的多形态） */
export type SettingsFieldValue =
  | string
  | number
  | boolean
  | Array<string | number>
  | null
  | undefined

export interface FieldVisibleWhen {
  key: string
  value: string | number | boolean
}

export interface FieldDisabledWhen {
  key: string
  value: string | number | boolean
}

/** el-date-picker disabled 回调的日期参数（Date 或 dayjs 对象） */
type DateLike = Date | { toDate: () => Date }

interface SettingsFieldBase {
  key: string
  label?: string
  required?: boolean
  description?: string
  fullRow?: boolean
  visibleWhen?: FieldVisibleWhen
  disabledWhen?: FieldDisabledWhen
  /** 平台配置透传字段（未声明的配置键原样透传） */
  [key: string]: unknown
}

export interface SettingsInputField extends SettingsFieldBase {
  type: 'input'
  placeholder?: string
}

export interface SettingsSwitchField extends SettingsFieldBase {
  type: 'switch'
}

export interface SettingsRadioOption {
  label: string
  value: string | boolean
}

export interface SettingsRadioField extends SettingsFieldBase {
  type: 'radio'
  options: SettingsRadioOption[]
}

export interface SettingsSelectOption {
  label: string
  value: string | number
}

export interface SettingsSelectField extends SettingsFieldBase {
  type: 'select' | 'multiSelect'
  placeholder?: string
  options?: SettingsSelectOption[]
}

export interface SettingsDateTimeField extends SettingsFieldBase {
  type: 'datetime' | 'date'
  placeholder?: string
  disabledDate?: (date: Date) => boolean
  disabledHours?: (role: string, comparingDate?: DateLike | null) => number[]
  disabledMinutes?: (hour: number, role: string, comparingDate?: DateLike | null) => number[]
}

export interface SettingsPoiField extends SettingsFieldBase {
  type: 'poiSelect'
  placeholder?: string
}

export interface SettingsCascaderOption {
  label: string
  value: string
  children?: SettingsCascaderOption[]
}

export interface SettingsCascaderField extends SettingsFieldBase {
  type: 'cascader'
  placeholder?: string
  options?: SettingsCascaderOption[]
  props?: Record<string, unknown>
}

export interface SettingsCompilationField extends SettingsFieldBase {
  type: 'compilationSelect'
  placeholder?: string
}

export type SettingsField =
  | SettingsInputField
  | SettingsSwitchField
  | SettingsRadioField
  | SettingsSelectField
  | SettingsDateTimeField
  | SettingsPoiField
  | SettingsCascaderField
  | SettingsCompilationField
