import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PublishSnapshot, { type BatchItem } from './PublishSnapshot.vue'

const ElIcon = { template: '<i class="el-icon-stub"><slot /></i>' }
const ElTag = { props: ['size'], template: '<span class="el-tag-stub"><slot /></span>' }

const successItem: BatchItem = {
  account_id: 1,
  status: 'success',
  account_configs: {
    title: '我的标题',
    description: '我的描述',
    tags: ['美食', '旅游'],
    creationDeclaration: '原创',
    scheduleTime: '2026-08-21 10:00:00',
  },
}

const mountIt = (over: any = {}) =>
  mount(PublishSnapshot, {
    props: {
      item: over.item ?? successItem,
      fallbackTitle: over.fallbackTitle ?? '兜底标题',
      fallbackDescription: over.fallbackDescription ?? '兜底描述',
      fallbackCoverUrl: over.fallbackCoverUrl ?? '',
    },
    global: { stubs: { ElIcon, ElTag } },
  })

describe('PublishSnapshot', () => {
  it('renders title, description, tags and meta fields', () => {
    const w = mountIt()
    expect(w.text()).toContain('我的标题')
    expect(w.text()).toContain('我的描述')
    expect(w.text()).toContain('#美食')
    expect(w.text()).toContain('#旅游')
    expect(w.text()).toContain('作品声明')
    expect(w.text()).toContain('原创')
    expect(w.text()).toContain('定时发布时间')
    expect(w.text()).toContain('2026-08-21 10:00:00')
    expect(w.classes()).not.toContain('content-snapshot--failed')
  })

  it('shows error banner and failed class when status is failed', () => {
    const w = mountIt({ item: { ...successItem, status: 'failed', error_message: '超时了' } })
    expect(w.classes()).toContain('content-snapshot--failed')
    expect(w.text()).toContain('发布失败')
    expect(w.text()).toContain('超时了')
  })

  it('shows placeholder when no cover url', () => {
    const w = mountIt({ item: { ...successItem, account_configs: {} } })
    expect(w.find('.cover-placeholder').exists()).toBe(true)
    expect(w.find('img').exists()).toBe(false)
  })

  it('uses coverLandscape url when present', () => {
    const item = { ...successItem, account_configs: { coverLandscape: { url: 'https://a/b.jpg' } } }
    const w = mountIt({ item })
    expect(w.find('img').attributes('src')).toBe('https://a/b.jpg')
  })

  it('falls back to batch cover url', () => {
    const w = mountIt({ item: { ...successItem, account_configs: {} }, fallbackCoverUrl: 'https://batch/cover.jpg' })
    expect(w.find('img').attributes('src')).toBe('https://batch/cover.jpg')
  })

  it('falls back to fallback title/description when fields missing', () => {
    const w = mountIt({ item: { ...successItem, account_configs: {} } })
    expect(w.text()).toContain('兜底标题')
    expect(w.text()).toContain('兜底描述')
  })
})
