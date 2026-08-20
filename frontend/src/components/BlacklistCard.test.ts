import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BlacklistCard from './BlacklistCard.vue'
import { ElButton, ElIcon } from '../../tests/stubs'

const platforms = [
  { key: 'xiaohongshu', name: '小红书', logo: '/xhs.png', cssClass: 'xiaohongshu' },
  { key: 'bilibili', name: 'B站', cssClass: 'bilibili' },
]

const mountIt = (over: Record<string, unknown> = {}) =>
  mount(BlacklistCard, {
    props: { platforms, ...over },
    global: { stubs: { ElButton, ElIcon } },
  })

describe('BlacklistCard', () => {
  it('渲染黑名单渠道 chip 列表', () => {
    const w = mountIt()
    expect(w.findAll('.blacklist-chip')).toHaveLength(2)
    expect(w.find('.chip-name').text()).toBe('小红书')
    expect(w.find('.chip-logo').attributes('src')).toBe('/xhs.png')
  })

  it('无 logo 渠道不渲染图片', () => {
    const w = mountIt()
    const chips = w.findAll('.blacklist-chip')
    expect(chips[1].find('.chip-logo').exists()).toBe(false)
  })

  it('空列表渲染空态', () => {
    const w = mountIt({ platforms: [] })
    expect(w.find('.blacklist-empty').exists()).toBe(true)
    expect(w.text()).toContain('暂无黑名单渠道')
  })

  it('点击「添加渠道」emit open', async () => {
    const w = mountIt()
    await w.find('.el-button-stub').trigger('click')
    expect(w.emitted('open')).toHaveLength(1)
  })

  it('点击移除按钮 emit remove(key) 且不冒泡', async () => {
    const w = mountIt()
    await w.findAll('.chip-remove')[0].trigger('click')
    expect(w.emitted('remove')).toEqual([['xiaohongshu']])
  })
})
