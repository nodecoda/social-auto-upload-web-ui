import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MaterialSelectToolbar from './MaterialSelectToolbar.vue'

const stubs = {
  ElInput: { props: ['modelValue', 'placeholder'], template: '<input :value="modelValue" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value); $emit(\'input\', $event)" @clear="$emit(\'clear\')" />' },
  ElIcon: { template: '<i class="el-icon-stub"><slot /></i>' },
}

const typeOptions = [
  { value: 'all', label: '全部', icon: 'Grid' },
  { value: 'image', label: '图片', icon: 'PictureFilled' },
  { value: 'video', label: '视频', icon: 'VideoCamera' },
]

const mountIt = (over: any = {}) =>
  mount(MaterialSelectToolbar, {
    props: { modelValue: '', typeOptions, typeFilter: 'all', ...over },
    global: { stubs },
  })

describe('MaterialSelectToolbar', () => {
  it('renders search input and type buttons', () => {
    const w = mountIt()
    expect(w.find('input').attributes('placeholder')).toBe('按文件名搜索...')
    const btns = w.findAll('.msd-type-btn')
    expect(btns).toHaveLength(3)
    expect(btns.map(b => b.text())).toEqual(['全部', '图片', '视频'])
  })

  it('marks active type button', () => {
    const w = mountIt({ typeFilter: 'image' })
    const btns = w.findAll('.msd-type-btn')
    expect(btns[1].classes()).toContain('active')
    expect(btns[0].classes()).not.toContain('active')
  })

  it('emits type-change when button clicked', async () => {
    const w = mountIt()
    await w.findAll('.msd-type-btn')[2].trigger('click')
    expect(w.emitted('type-change')).toEqual([['video']])
  })

  it('emits search-input on typing and updates modelValue', async () => {
    const w = mountIt()
    await w.find('input').setValue('abc')
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual(['abc'])
    expect(w.emitted('search-input')!.length).toBeGreaterThan(0)
  })
})
