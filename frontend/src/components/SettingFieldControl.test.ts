import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingFieldControl from './SettingFieldControl.vue'

const stubs = {
  ElInput: { template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  ElSwitch: { template: '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />' },
  ElSelect: { template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>' },
  ElOption: { props: ['value', 'label'], template: '<option :value="value">{{ label }}</option>' },
  ElDatePicker: { template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  ElCascader: { template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  XhsPoiSelect: { template: '<div class="xhs-poi-stub" @click="$emit(\'change\', { name: \'北京\' })" />' },
  VivoPositionSelect: { template: '<div class="vivo-poi-stub" />' },
  RemoteSearchSelect: { template: '<div class="remote-stub" @click="$emit(\'change\', { compilationId: 9 })" />' },
}

const mountIt = (field: any, modelValue: any = null, form: any = {}, over: any = {}) =>
  mount(SettingFieldControl, {
    props: {
      field,
      modelValue,
      form,
      platformColor: '#ff0000',
      selectedAccountId: 1,
      selectedPlatform: 'test',
      ...over,
    },
    global: { stubs },
  })

describe('SettingFieldControl', () => {
  it('renders input for input type and emits update:modelValue', async () => {
    const w = mountIt({ key: 'caption', type: 'input', placeholder: '输入标题' }, '')
    const input = w.find('input')
    expect(input.attributes('placeholder')).toBe('输入标题')
    await input.setValue('新标题')
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual(['新标题'])
  })

  it('renders switch for switch type', () => {
    const w = mountIt({ key: 'flag', type: 'switch' }, true)
    expect(w.find('input[type="checkbox"]').exists()).toBe(true)
  })

  it('renders radio options and disables when disabledWhen matches form', () => {
    const field = { key: 'source', type: 'radio', options: [{ value: 'a', label: '原创' }, { value: 'b', label: '转载' }], disabledWhen: { key: 'locked', value: true } }
    const w = mountIt(field, 'a', { locked: true })
    const radios = w.findAll('input[type="radio"]')
    expect(radios).toHaveLength(2)
    expect(radios[0].attributes('disabled')).toBeDefined()
    expect(w.find('.radio-row').classes()).toContain('is-disabled')
  })

  it('renders select for select/multiSelect type with options', () => {
    const w = mountIt({ key: 'kind', type: 'select', options: [{ value: 'x', label: 'X' }] })
    expect(w.find('select').exists()).toBe(true)
    expect(w.text()).toContain('X')
  })

  it('renders date pickers for datetime/date types', () => {
    const dt = mountIt({ key: 'scheduleTime', type: 'datetime' }, null, { scheduleTime: null })
    expect(dt.find('input').exists()).toBe(true)
    const d = mountIt({ key: 'date', type: 'date' }, null, {})
    expect(d.find('input').exists()).toBe(true)
  })

  it('dispatches poiSelect to xhs/vivo by key prefix', () => {
    const xhs = mountIt({ key: 'poi', type: 'poiSelect' })
    expect(xhs.find('.xhs-poi-stub').exists()).toBe(true)
    const vivo = mountIt({ key: 'vivoPoi', type: 'poiSelect' })
    expect(vivo.find('.vivo-poi-stub').exists()).toBe(true)
  })

  it('emits poi-change with field key and payload', async () => {
    const w = mountIt({ key: 'poi', type: 'poiSelect' })
    await w.find('.xhs-poi-stub').trigger('click')
    expect(w.emitted('poi-change')!.at(-1)).toEqual(['poi', { name: '北京' }])
  })

  it('emits compilation-change for compilationSelect', async () => {
    const w = mountIt({ key: 'compilation', type: 'compilationSelect' }, null, {})
    await w.find('.remote-stub').trigger('click')
    expect(w.emitted('compilation-change')!.at(-1)).toEqual(['compilation', { compilationId: 9 }])
  })

  it('renders cascader for cascader type', () => {
    const w = mountIt({ key: 'cascader', type: 'cascader', options: [] })
    expect(w.find('input').exists()).toBe(true)
  })
})
