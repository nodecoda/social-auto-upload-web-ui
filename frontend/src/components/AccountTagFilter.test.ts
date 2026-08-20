import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AccountTagFilter from './AccountTagFilter.vue'

const stubs = {
  ElInput: { props: ['modelValue', 'placeholder'], template: '<input :value="modelValue" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  ElButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  ElIcon: { template: '<i class="el-icon-stub"><slot /></i>' },
}

const tags = [
  { id: 1, name: '美食', color: '#ff0000' },
  { id: 2, name: '旅游', color: '#00ff00' },
  { id: 3, name: '美食探店', color: '#0000ff' },
]

const mountIt = (over: any = {}) =>
  mount(AccountTagFilter, {
    props: {
      allTags: tags,
      selectedTagIds: new Set([1]),
      modelValue: '',
      ...over,
    },
    global: { stubs },
  })

describe('AccountTagFilter', () => {
  it('renders title, selected count and all tag chips', () => {
    const w = mountIt()
    expect(w.text()).toContain('标签筛选')
    expect(w.text()).toContain('已选 1')
    expect(w.text()).toContain('美食')
    expect(w.text()).toContain('旅游')
    expect(w.findAll('.tag-chip')).toHaveLength(3)
  })

  it('marks selected chips and shows check icon', () => {
    const w = mountIt()
    expect(w.find('.tag-chip.selected').text()).toContain('美食')
    expect(w.find('.tag-check').exists()).toBe(true)
  })

  it('filters tags by keyword', async () => {
    const w = mountIt()
    await w.setProps({ modelValue: '旅游' })
    expect(w.findAll('.tag-chip')).toHaveLength(1)
    expect(w.text()).toContain('旅游')
    expect(w.text()).not.toContain('美食')
  })

  it('emits toggle-tag when chip clicked', async () => {
    const w = mountIt()
    await w.findAll('.tag-chip')[1].trigger('click') // 旅游
    expect(w.emitted('toggle-tag')).toEqual([[2]])
  })

  it('emits clear-all when 全不选 clicked', async () => {
    const w = mountIt()
    const btn = w.findAll('button').find(b => b.text().includes('全不选'))!
    await btn.trigger('click')
    expect(w.emitted('clear-all')).toHaveLength(1)
  })

  it('shows empty hints for no tags / no matches', async () => {
    const w = mountIt({ allTags: [] })
    expect(w.text()).toContain('暂无标签')
    const w2 = mountIt()
    await w2.setProps({ modelValue: '不存在的标签' })
    expect(w2.text()).toContain('没有匹配的标签')
  })

  it('updates modelValue on search input', async () => {
    const w = mountIt()
    await w.find('input').setValue('美食探店')
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual(['美食探店'])
  })
})
