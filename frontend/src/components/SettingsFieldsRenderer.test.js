import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsFieldsRenderer from './SettingsFieldsRenderer.vue'

const stubs = {
  ElInput: { template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  ElSwitch: { template: '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />' },
  ElSelect: { template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>' },
  ElOption: { template: '<option :value="value">{{ label }}</option>' },
  ElDatePicker: { template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  ElCascader: { template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  XhsPoiSelect: { template: '<div class="xhs-poi-stub" @click="$emit(\'change\', { name: \'北京\' })" />' },
  VivoPositionSelect: { template: '<div class="vivo-poi-stub" />' },
  RemoteSearchSelect: { template: '<div class="remote-stub" @click="$emit(\'change\', { compilationId: 9 })" />' },
}

function makeForm() {
  return { title: '', scheduleTime: null, poi: null, poiData: null, flag: true, source: 'a', tags: [], kind: '', compilation: null }
}

const platform = { color: '#ff0000', key: 'test', name: '测试' }

const fields = [
  { key: 'caption', label: '标题', type: 'input', placeholder: '输入标题' },
  { key: 'flag', label: '开关', type: 'switch' },
  { key: 'source', label: '来源', type: 'radio', options: [{ value: 'a', label: '原创' }, { value: 'b', label: '转载' }] },
  { key: 'kind', label: '类型', type: 'select', options: [{ value: 'x', label: 'X' }] },
  { key: 'tags', label: '标签', type: 'multiSelect', options: [{ value: 't', label: 'T' }] },
  { key: 'scheduleTime', label: '定时', type: 'datetime' },
  { key: 'date', label: '日期', type: 'date' },
  { key: 'poi', label: '地点', type: 'poiSelect' },
  { key: 'vivoPoi', label: 'VIVO地点', type: 'poiSelect' },
  { key: 'compilation', label: '合集', type: 'compilationSelect' },
  { key: 'cascader', label: '级联', type: 'cascader', options: [] },
  { key: 'hidden', label: '隐藏', type: 'input', visibleWhen: { key: 'source', value: 'never' } },
]

const mountIt = (over = {}) => mount(SettingsFieldsRenderer, {
  props: { fields, form: makeForm(), platform, selectedPlatform: 'test', selectedAccountId: 1, ...over },
  global: { stubs },
})

describe('SettingsFieldsRenderer', () => {
  it('按配置渲染各类型字段', () => {
    const w = mountIt()
    expect(w.find('.setting-card').exists()).toBe(true)
    expect(w.findAll('.setting-card')).toHaveLength(11) // hidden 字段被 visibleWhen 过滤
  })

  it('visibleWhen 不满足时不渲染字段', () => {
    const w = mountIt()
    expect(w.text()).not.toContain('隐藏')
  })

  it('input 字段 v-model 写回 form', async () => {
    const w = mountIt()
    const input = w.find('input[type="text"], input:not([type])')
    // 找标题输入框（placeholder）
    const title = w.findAll('input').find(i => i.attributes('placeholder') === '输入标题')
    await title.setValue('我的标题')
    expect(w.props('form').caption).toBe('我的标题')
  })

  it('radio 字段渲染选项并支持选中', async () => {
    const w = mountIt()
    const radios = w.findAll('input[type="radio"]')
    expect(radios).toHaveLength(2)
    await radios[1].setValue()
    expect(w.props('form').source).toBe('b')
  })

  it('poiSelect 按 key 前缀分发 xhs/vivo 组件', () => {
    const w = mountIt()
    expect(w.find('.xhs-poi-stub').exists()).toBe(true)
    expect(w.find('.vivo-poi-stub').exists()).toBe(true)
  })

  it('poi change 把完整对象写入 <key>Data', async () => {
    const w = mountIt()
    await w.find('.xhs-poi-stub').trigger('click')
    expect(w.props('form').poiData).toEqual({ name: '北京' })
  })

  it('compilationSelect 渲染 RemoteSearchSelect 并回调写入 compilationData', async () => {
    const w = mountIt()
    const stubs2 = w.findAll('.remote-stub')
    expect(stubs2.length).toBeGreaterThan(0)
    await stubs2[0].trigger('click')
    expect(w.props('form').compilationData).toEqual({ compilationId: 9 })
  })
})
