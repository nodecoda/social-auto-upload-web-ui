import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import FeedbackCard from './FeedbackCard.vue'
import { ElIcon, ElTag } from '../../tests/stubs'

const fb = {
  id: 1,
  status: 2,
  content: '希望支持多平台同时发布',
  email: 'user123@example.com',
  created_at: '2026-08-20T10:30:00',
  vote_count: 5,
  attachments: [{ id: 1, file_url: '/a.png' }],
}

const mountIt = (over: Record<string, unknown> = {}) =>
  mount(FeedbackCard, {
    props: { fb, voted: false, ...over },
    global: { stubs: { ElIcon, ElTag } },
  })

describe('FeedbackCard', () => {
  it('渲染状态标签、截断内容、脱敏邮箱与时间', () => {
    const w = mountIt()
    expect(w.find('.el-tag-stub').text()).toContain('处理中')
    expect(w.text()).toContain('希望支持多平台同时发布')
    expect(w.text()).toContain('us***@example.com')
    expect(w.find('.meta-time').text()).toMatch(/2026/)
  })

  it('渲染投票数与附件数量', () => {
    const w = mountIt()
    expect(w.text()).toContain('5')
    expect(w.text()).toContain('1 个附件')
  })

  it('已投票态显示「已支持」并禁用按钮', () => {
    const w = mountIt({ voted: true })
    const btn = w.find('.vote-btn')
    expect(btn.text()).toContain('已支持')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('无附件时隐藏附件行', () => {
    const w = mountIt({ fb: { ...fb, attachments: [] } })
    expect(w.find('.card-attachments').exists()).toBe(false)
  })

  it('点击卡片 emit open, 点击投票按钮 emit vote(不冒泡到 open)', async () => {
    const w = mountIt()
    await w.find('.feedback-card').trigger('click')
    expect(w.emitted('open')).toEqual([[fb]])
    await w.find('.vote-btn').trigger('click')
    expect(w.emitted('vote')).toEqual([[fb]])
    expect(w.emitted('open')).toHaveLength(1)
  })

  it('已投票卡片点击投票不 emit', async () => {
    const w = mountIt({ voted: true })
    await w.find('.vote-btn').trigger('click')
    expect(w.emitted('vote')).toBeUndefined()
  })
})
