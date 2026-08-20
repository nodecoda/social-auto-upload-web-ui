import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import QuickActionCard from './QuickActionCard.vue'

describe('QuickActionCard', () => {
  it('renders title, desc and variant icon class', () => {
    const wrapper = mount(QuickActionCard, {
      props: {
        variant: 'purple',
        title: '快速发布',
        desc: '发布内容到各平台',
        route: '/publish-center',
      },
    })
    expect(wrapper.find('.action-card').exists()).toBe(true)
    expect(wrapper.find('.action-icon-purple').exists()).toBe(true)
    expect(wrapper.text()).toContain('快速发布')
    expect(wrapper.text()).toContain('发布内容到各平台')
  })

  it('emits navigate with route when clicked', async () => {
    const wrapper = mount(QuickActionCard, {
      props: {
        variant: 'blue',
        title: '上传素材',
        desc: '上传和管理视频素材',
        route: '/material-management',
      },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('navigate')).toHaveLength(1)
    expect(wrapper.emitted('navigate')![0]).toEqual(['/material-management'])
  })

  it('renders icon slot content', () => {
    const wrapper = mount(QuickActionCard, {
      props: {
        variant: 'green',
        title: '账号管理',
        desc: '管理所有平台账号',
        route: '/account-management',
      },
      slots: { icon: '<span class="fake-icon">I</span>' },
    })
    expect(wrapper.find('.fake-icon').exists()).toBe(true)
  })
})
