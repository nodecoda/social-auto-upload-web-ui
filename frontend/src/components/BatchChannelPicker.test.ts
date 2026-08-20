import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BatchChannelPicker from './BatchChannelPicker.vue'
import { type ExtractPropTypes } from 'vue'

const platforms = [
  { key: 'douyin', name: '抖音', count: 3 },
  { key: 'xiaohongshu', name: '小红书', count: 0 },
  { key: 'bilibili', name: 'B站', count: 2, logo: '/logo.png' },
]

const mountIt = (over: Partial<ExtractPropTypes<typeof BatchChannelPicker['props']>> = {}) =>
  mount(BatchChannelPicker, {
    props: { platforms, checkedKeys: new Set(['douyin']), ...over },
  })

describe('BatchChannelPicker', () => {
  it('renders all channel cards with name and count', () => {
    const w = mountIt()
    const cards = w.findAll('.channel-card')
    expect(cards).toHaveLength(3)
    expect(w.text()).toContain('抖音')
    expect(w.text()).toContain('小红书')
    expect(cards[2].find('img').exists()).toBe(true)
  })

  it('marks checked and disabled states', () => {
    const w = mountIt()
    const cards = w.findAll('.channel-card')
    expect(cards[0].classes()).toContain('is-checked')
    expect(cards[1].classes()).toContain('is-disabled')
    expect(cards[1].attributes('aria-disabled')).toBe('true')
    expect(cards[1].attributes('tabindex')).toBe('-1')
  })

  it('emits toggle with platform on click', async () => {
    const w = mountIt()
    await w.findAll('.channel-card')[2].trigger('click')
    expect(w.emitted('toggle')).toEqual([[platforms[2]]])
  })

  it('emits toggle on keyboard enter/space', async () => {
    const w = mountIt()
    const card = w.findAll('.channel-card')[0]
    await card.trigger('keydown.enter')
    await card.trigger('keydown.space')
    expect(w.emitted('toggle')).toHaveLength(2)
  })
})
