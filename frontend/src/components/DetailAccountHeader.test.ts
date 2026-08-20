import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DetailAccountHeader from './DetailAccountHeader.vue'

const item = {
  account_id: 1,
  status: 'success',
  created_at: '2026-08-20T10:00:00',
  duration: 125,
  publish_url: 'https://example.com/p/1',
}

const account = { name: '测试账号' }
const platformConfig = { color: '#ff0000', name: '抖音' }

const mountIt = (over: Record<string, unknown> = {}) =>
  mount(DetailAccountHeader, {
    props: { item, account, platformConfig, ...over },
  })

describe('DetailAccountHeader', () => {
  it('渲染账号名、平台徽章、状态、时间与耗时', () => {
    const w = mountIt()
    expect(w.find('.account-name').text()).toBe('测试账号')
    expect(w.find('.platform-badge').text()).toBe('抖音')
    expect(w.find('.status-tag').text()).toBe('全部成功')
    expect(w.text()).toContain('耗时 2分5秒')
  })

  it('成功且有发布链接时显示查看链接', () => {
    const w = mountIt()
    const link = w.find('.view-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://example.com/p/1')
  })

  it('非成功状态隐藏发布链接', () => {
    const w = mountIt({ item: { ...item, status: 'failed', publish_url: undefined } })
    expect(w.find('.view-link').exists()).toBe(false)
  })

  it('账号已删除时显示占位', () => {
    const w = mountIt({ account: null, platformConfig: null })
    expect(w.find('.account-name').text()).toBe('已删除账号')
    expect(w.find('.platform-badge').exists()).toBe(false)
    expect(w.find('.avatar').text()).toBe('?')
  })
})
