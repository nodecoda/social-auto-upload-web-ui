import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatCard from './StatCard.vue'

describe('StatCard', () => {
  it('renders variant class, value and label', () => {
    const wrapper = mount(StatCard, {
      props: { variant: 'purple', value: 3, label: '账号总数' },
    })
    expect(wrapper.find('.stat-card.stat-purple').exists()).toBe(true)
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('账号总数')
  })

  it('renders details as label: value pairs separated by dividers', () => {
    const wrapper = mount(StatCard, {
      props: {
        variant: 'cyan',
        value: 5,
        label: '素材总数',
        details: [
          { label: '视频', value: 2 },
          { label: '图片', value: 3 },
          { label: '其他', value: 0 },
        ],
      },
    })
    expect(wrapper.text()).toContain('视频: 2')
    expect(wrapper.text()).toContain('图片: 3')
    expect(wrapper.text()).toContain('其他: 0')
    expect(wrapper.findAll('.divider')).toHaveLength(2)
  })

  it('renders no stat-detail when details are empty', () => {
    const wrapper = mount(StatCard, {
      props: { variant: 'blue', value: 1, label: '已接入平台' },
    })
    expect(wrapper.find('.stat-detail').exists()).toBe(false)
  })

  it('renders icon slot content', () => {
    const wrapper = mount(StatCard, {
      props: { variant: 'blue', value: 1, label: '已接入平台' },
      slots: { icon: '<span class="fake-icon">I</span>' },
    })
    expect(wrapper.find('.fake-icon').exists()).toBe(true)
  })

  it('renders extra slot content inside stat-top', () => {
    const wrapper = mount(StatCard, {
      props: { variant: 'purple', value: 1, label: '账号总数' },
      slots: { extra: '<button class="batch-check-btn">批量检查</button>' },
    })
    expect(wrapper.find('.stat-top .batch-check-btn').exists()).toBe(true)
  })

  it('prefers custom bottom slot over details', () => {
    const wrapper = mount(StatCard, {
      props: {
        variant: 'green',
        value: '—',
        label: '今日发布',
        details: [{ label: '成功率', value: '—' }],
      },
      slots: { bottom: '<div class="custom-bottom">custom</div>' },
    })
    expect(wrapper.find('.custom-bottom').exists()).toBe(true)
    expect(wrapper.find('.stat-detail').exists()).toBe(false)
  })

  it('renders numeric value zero', () => {
    const wrapper = mount(StatCard, {
      props: { variant: 'cyan', value: 0, label: '素材总数' },
    })
    expect(wrapper.find('.stat-value').text()).toBe('0')
  })
})
