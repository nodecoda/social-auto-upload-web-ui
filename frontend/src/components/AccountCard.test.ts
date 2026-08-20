import { describe, it, expect } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import AccountCard from './AccountCard.vue'
import { ElIcon, ElTag } from '../../tests/stubs'
import type { AccountItem } from './accountCardShared'

/** TagPopover:仅渲染触发按钮插槽,不加载真实 api 依赖 */
const TagPopoverStub = {
  name: 'TagPopover',
  props: ['visible', 'accountId', 'selectedTags'],
  emits: ['update:visible', 'changed'],
  template: '<div class="tag-popover-stub"><slot /></div>',
}

const base: AccountItem = {
  id: 1, type: 2, filePath: '', name: '测试账号', status: '正常',
  platform: '抖音', avatar: '', fans: 100, likes: 50, follows: 10,
  stats: [], tags: [],
}

const mountIt = (over: Record<string, unknown> = {}) =>
  mount(AccountCard, {
    props: {
      account: base,
      checkingIds: new Set<string | number>(),
      syncingIds: new Set<string | number>(),
      tagOverflowMap: {},
      disabled: false,
      ...over,
    },
    global: { stubs: { ElIcon, ElTag, TagPopover: TagPopoverStub } },
  })

const btn = (w: VueWrapper, label: string) =>
  w.findAll('.action-btn').find(b => b.text().includes(label))!

describe('AccountCard', () => {
  it('渲染账号名、平台、状态徽章与头像(默认头像回退)', () => {
    const w = mountIt()
    expect(w.find('.user-name').text()).toBe('测试账号')
    expect(w.find('.platform-name').text()).toBe('抖音')
    expect(w.find('.status-badge').text()).toContain('正常')
    const avatar = w.find('img.user-avatar')
    expect(avatar.attributes('src')).toContain('ui-avatars.com')
  })

  it('正常状态渲染「检查」按钮并 emit check', async () => {
    const w = mountIt()
    await btn(w, '检查').trigger('click')
    expect(w.emitted('check')).toEqual([[base]])
    expect(w.find('.action-btn.login').exists()).toBe(false)
  })

  it('异常状态渲染「登录」按钮并 emit relogin', async () => {
    const account = { ...base, status: '异常' }
    const w = mountIt({ account })
    await btn(w, '登录').trigger('click')
    expect(w.emitted('relogin')).toEqual([[account]])
    expect(w.find('.action-btn.check').exists()).toBe(false)
  })

  it('disabled 时显示已拉黑标签并禁用登录/同步/创作中心按钮', () => {
    const account = { ...base, status: '异常' }
    const w = mountIt({ disabled: true, account })
    expect(w.find('.disabled-tag').text()).toBe('已拉黑')
    // disabled 时登录按钮文案变为「已拉黑」,但仍可通过 .action-btn.login 定位
    const login = w.find('.action-btn.login')
    expect(login.text()).toContain('已拉黑')
    expect(login.attributes('disabled')).toBeDefined()
    expect(btn(w, '同步').attributes('disabled')).toBeDefined()
    expect(btn(w, '创作中心').attributes('disabled')).toBeDefined()
  })

  it('同步/创作中心/删除按钮分别 emit sync/creator/delete', async () => {
    const w = mountIt()
    await btn(w, '同步').trigger('click')
    await btn(w, '创作中心').trigger('click')
    await btn(w, '删除').trigger('click')
    expect(w.emitted('sync')).toEqual([[base]])
    expect(w.emitted('creator')).toEqual([[base]])
    expect(w.emitted('delete')).toEqual([[base]])
  })

  it('无运营数据时显示空态提示', () => {
    const w = mountIt()
    expect(w.find('.stat-block-empty').text()).toContain('暂无运营数据')
  })

  it('渲染运营数据块并格式化数值(10000 → 1.0w)', () => {
    const w = mountIt({ account: { ...base, stats: [{ ICON: 'FANS', COUNT: 10000, NAME: '粉丝', SORT: 1 }] } })
    const block = w.find('.stat-block')
    expect(block.find('.stat-value').text()).toBe('1.0w')
    expect(block.find('.stat-label').text()).toBe('粉丝')
  })

  it('B站超 3 项显示「更多」占位,浮窗列出全部额外项', () => {
    const stats = [1, 2, 3, 4, 5].map(i => ({ ICON: 'user', COUNT: i * 1000, NAME: `指标${i}`, SORT: i }))
    const w = mountIt({ account: { ...base, platform: 'B站', stats } })
    const more = w.find('.stats-more-wrap')
    expect(more.exists()).toBe(true)
    expect(more.find('.stat-value').text()).toBe('+2')
    const items = more.findAll('.stats-more-item')
    expect(items).toHaveLength(5)
    expect(items.map(i => i.find('.name').text())).toEqual(['指标1', '指标2', '指标3', '指标4', '指标5'])
  })

  it('渲染标签,点击 × 移除 emit remove-tag(account, tag)', async () => {
    const tags = [{ id: 7, name: '科技', color: '#ff0000' }]
    const account = { ...base, tags }
    const w = mountIt({ account })
    expect(w.find('.account-tag').text()).toContain('科技')
    await w.find('.account-tag-remove').trigger('click')
    expect(w.emitted('remove-tag')).toEqual([[account, tags[0]]])
  })

  it('无标签时不渲染标签轨道', () => {
    const w = mountIt()
    expect(w.find('.account-tags-viewport').exists()).toBe(false)
  })
})
