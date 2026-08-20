import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChannelSummary from './ChannelSummary.vue'

const channels = [
  { platform: 'douyin', name: '抖音', count: 3, logo: '/logos/douyin.png' },
  { platform: 'bilibili', name: 'B站', count: 5, logo: '' },
]

describe('ChannelSummary', () => {
  it('渲染每个渠道的名称和数量', () => {
    const w = mount(ChannelSummary, { props: { channels } })
    const tags = w.findAll('.channel-tag')
    expect(tags).toHaveLength(2)
    expect(w.text()).toContain('抖音 × 3')
    expect(w.text()).toContain('B站 × 5')
  })

  it('有 logo 的渠道渲染 img，无 logo 的不渲染', () => {
    const w = mount(ChannelSummary, { props: { channels } })
    const imgs = w.findAll('img')
    expect(imgs).toHaveLength(1)
    expect(imgs[0].attributes('src')).toBe('/logos/douyin.png')
  })

  it('channels 为空时不渲染任何标签', () => {
    const w = mount(ChannelSummary, { props: { channels: [] } })
    expect(w.findAll('.channel-tag')).toHaveLength(0)
  })
})
