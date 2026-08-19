import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { ElTooltip, ElIcon } from '../../tests/stubs.js'
import PublishStats from './PublishStats.vue'

const mountIt = (over = {}) => mount(PublishStats, {
  props: { ...over },
  global: { stubs: { ElTooltip, ElIcon } },
})

describe('PublishStats', () => {
  it('渲染四个指标标签与格式化数值(zh-CN 千分位)', () => {
    const w = mountIt({ views: 1234, likes: 5678, favorites: 900, comments: 100 })
    const labels = w.findAll('.stat-label').map(n => n.text())
    expect(labels).toEqual(['播放', '点赞', '收藏', '评论'])
    const values = w.findAll('.stat-value').map(n => n.text())
    expect(values).toEqual(['1,234', '5,678', '900', '100'])
  })

  it('null 值渲染占位「--」并带 placeholder 类', () => {
    const w = mountIt({ views: null, likes: null, favorites: null, comments: null })
    const values = w.findAll('.stat-value').map(n => n.text())
    expect(values).toEqual(['--', '--', '--', '--'])
    const items = w.findAll('.stat-item')
    expect(items.every(i => i.classes().includes('stat-item--placeholder'))).toBe(true)
  })

  it('大数字格式化为 w(万)单位', () => {
    const w = mountIt({ views: 123456, likes: 10000 })
    const values = w.findAll('.stat-value').map(n => n.text())
    expect(values[0]).toBe('12.3w')
    expect(values[1]).toBe('1.0w')
    // 未传的指标仍为占位
    expect(values[2]).toBe('--')
  })

  it('字符串数值原样透传', () => {
    const w = mountIt({ views: '1.2万', likes: '未知' })
    const values = w.findAll('.stat-value').map(n => n.text())
    expect(values[0]).toBe('1.2万')
    expect(values[1]).toBe('未知')
  })

  it('compact 模式:根节点与 stat-inner 带 compact 类', () => {
    const w = mountIt({ compact: true, views: 1, likes: 1, favorites: 1, comments: 1 })
    expect(w.classes()).toContain('publish-stats--compact')
    expect(w.find('.stat-inner').classes()).toContain('stat-inner--compact')
    const w2 = mountIt({ views: 1, likes: 1, favorites: 1, comments: 1 })
    expect(w2.classes()).not.toContain('publish-stats--compact')
  })

  it('每个指标项应用对应主题色类', () => {
    const w = mountIt({ views: 1, likes: 2, favorites: 3, comments: 4 })
    const classes = w.findAll('.stat-item').map(i => i.classes().find(c => c.startsWith('stat-item--') && c !== 'stat-item--placeholder'))
    expect(classes).toEqual(['stat-item--blue', 'stat-item--rose', 'stat-item--cyan', 'stat-item--green'])
  })
})
