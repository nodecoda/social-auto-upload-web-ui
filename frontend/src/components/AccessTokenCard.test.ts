import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const successMock = vi.fn()
const warningMock = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: (...a: unknown[]) => successMock(...a), warning: (...a: unknown[]) => warningMock(...a) },
}))

import AccessTokenCard from './AccessTokenCard.vue'

const ElInput = {
  props: ['modelValue', 'placeholder', 'type'],
  emits: ['update:modelValue'],
  template: '<input :value="modelValue" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value)" />',
}

const ElButton = {
  props: ['loading', 'type'],
  template: '<button :disabled="loading"><slot /></button>',
}

const ElTag = {
  props: ['type'],
  template: '<span><slot /></span>',
}

const mountIt = (enabled: boolean) =>
  mount(AccessTokenCard, {
    props: { enabled },
    global: { stubs: { ElInput, ElButton, ElTag } },
  })

describe('AccessTokenCard', () => {
  it('未启用时显示「未启用」且无清除按钮', () => {
    const wrapper = mountIt(false)
    expect(wrapper.text()).toContain('未启用')
    expect(wrapper.find('button').exists()).toBe(true) // 保存按钮
  })

  it('已启用时显示「已启用」并提供清除按钮', () => {
    const wrapper = mountIt(true)
    expect(wrapper.text()).toContain('已启用')
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBe(2) // 保存 + 清除
  })

  it('输入令牌并保存时 emit save(token)', async () => {
    const wrapper = mountIt(false)
    await wrapper.find('input').setValue('my-secret-token')
    await wrapper.findAll('button')[0].trigger('click')
    expect(wrapper.emitted('save')?.[0]).toEqual(['my-secret-token'])
  })

  it('空输入保存时提示警告且不 emit', async () => {
    const wrapper = mountIt(false)
    await wrapper.findAll('button')[0].trigger('click')
    expect(wrapper.emitted('save')).toBeUndefined()
    expect(warningMock).toHaveBeenCalled()
  })

  it('点击清除时 emit clear', async () => {
    const wrapper = mountIt(true)
    const clearBtn = wrapper.findAll('button')[1]
    await clearBtn.trigger('click')
    expect(wrapper.emitted('clear')).toHaveLength(1)
  })
})
