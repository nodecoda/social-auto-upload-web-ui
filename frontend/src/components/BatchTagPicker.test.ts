import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BatchTagPicker from './BatchTagPicker.vue'

const ElInput = {
  props: ['modelValue', 'placeholder'],
  template: `
    <div class="el-input-stub">
      <input :value="modelValue" :placeholder="placeholder"
        @input="$emit('update:modelValue', $event.target.value)"
        @keyup.enter="$emit('keyup:enter', $event)" />
      <slot name="append" />
    </div>
  `,
}

const ElButton = {
  props: ['disabled'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
}

const ElIcon = { template: '<i class="el-icon-stub"><slot /></i>' }

const tags = [
  { id: 1, name: '美食', color: '#ff0000' },
  { id: 2, name: '旅游', color: '#00ff00' },
]

const mountIt = (over: any = {}) =>
  mount(BatchTagPicker, {
    props: { tags, selectedTagIds: new Set([1]), modelValue: '', ...over },
    global: { stubs: { ElInput, ElButton, ElIcon } },
  })

describe('BatchTagPicker', () => {
  it('renders title, selected count and tag chips', () => {
    const w = mountIt()
    expect(w.text()).toContain('选择标签')
    expect(w.text()).toContain('已选 1')
    expect(w.findAll('.batch-tag-chip')).toHaveLength(2)
  })

  it('marks selected chip with check icon', () => {
    const w = mountIt()
    expect(w.find('.batch-tag-chip.selected').exists()).toBe(true)
    expect(w.find('.batch-tag-check').exists()).toBe(true)
  })

  it('filters tags by keyword', async () => {
    const w = mountIt()
    await w.setProps({ modelValue: '旅游' })
    expect(w.findAll('.batch-tag-chip')).toHaveLength(1)
    expect(w.text()).toContain('旅游')
  })

  it('emits toggle-tag and delete-tag on chip interactions', async () => {
    const w = mountIt()
    await w.findAll('.batch-tag-chip')[1].trigger('click')
    expect(w.emitted('toggle-tag')).toEqual([[tags[1]]])
    await w.find('.batch-tag-delete').trigger('click')
    expect(w.emitted('delete-tag')).toEqual([[tags[0]]])
  })

  it('emits create on enter key and button click', async () => {
    const w = mountIt()
    await w.find('input').trigger('keyup.enter')
    expect(w.emitted('create')!.length).toBeGreaterThanOrEqual(1)
    // 按钮在关键词为空时禁用,输入后再点
    await w.setProps({ modelValue: '新标签' })
    await w.find('button').trigger('click')
    expect(w.emitted('create')!.length).toBeGreaterThanOrEqual(2)
  })

  it('shows empty hint when no matching tags', async () => {
    const w = mountIt({ modelValue: '不存在' })
    expect(w.text()).toContain('暂无标签,输入名称按回车创建')
  })
})
