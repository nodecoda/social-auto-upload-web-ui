import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ElIcon } from '../../tests/stubs.js'
import AccountSidebar from './AccountSidebar.vue'

// 可控的 appStore mock:isPlatformDisabled 默认返回 false,可按用例覆写
const { isPlatformDisabled } = vi.hoisted(() => ({ isPlatformDisabled: vi.fn(() => false) }))
vi.mock('@/stores/app', () => ({
  useAppStore: () => ({ isPlatformDisabled }),
}))

const groups = [
  {
    key: 'douyin', name: '抖音', color: '#000000', letter: '抖', logo: '',
    accounts: [
      { id: 1, name: '账号A', status: '正常', avatar: '' },
      { id: 2, name: '账号B', status: '异常', avatar: 'http://sinaimg.cn/a/b.jpg' },
    ],
  },
  {
    key: 'kuaishou', name: '快手', color: '#ff0000', letter: '快', logo: '',
    accounts: [{ id: 3, name: '账号C', status: '正常', avatar: '' }],
  },
  {
    key: 'blocked', name: '被禁用平台', color: '#888888', letter: '禁', logo: '',
    accounts: [{ id: 9, name: '账号X', status: '正常', avatar: '' }],
  },
]

const defaultProps = () => ({
  mode: 'edit',
  accountGroups: groups,
  totalCount: 3,
  selectedPlatform: null,
  selectedAccountId: null,
  expandedGroups: new Set(['douyin']),
  publishAccountIds: new Set([1, 2]),
  hasAccountOverride: vi.fn(() => false),
})

const mountIt = (over = {}) => mount(AccountSidebar, {
  props: { ...defaultProps(), ...over },
  global: { stubs: { ElIcon } },
})

describe('AccountSidebar', () => {
  beforeEach(() => {
    isPlatformDisabled.mockReset()
    isPlatformDisabled.mockReturnValue(false)
  })

  it('渲染标题与总账号数', () => {
    const w = mountIt()
    expect(w.find('.sidebar-title').text()).toBe('账号管理')
    expect(w.find('.sidebar-count').text()).toBe('3')
  })

  it('edit 模式:未选账号时显示空态提示,且不渲染无已选账号的分组', () => {
    const w = mountIt({ publishAccountIds: new Set() })
    expect(w.text()).toContain('暂无选中账号')
    expect(w.text()).toContain('点击下方「账号设置」开始')
    expect(w.findAll('.group-wrap')).toHaveLength(0)
  })

  it('edit 模式:只显示含已选账号的分组,账号列表按 publishAccountIds 过滤,计数正确', () => {
    const w = mountIt({ publishAccountIds: new Set([1]) })
    // kuaishou / blocked 分组被过滤
    const names = w.findAll('.group-name').map(n => n.text())
    expect(names).toEqual(['抖音'])
    // 只渲染已选中的账号
    const accounts = w.findAll('.account-item')
    expect(accounts).toHaveLength(1)
    expect(accounts[0].text()).toContain('账号A')
    // 分组计数 = 已选账号数
    expect(w.find('.group-count').text()).toBe('1')
    // 无空态提示
    expect(w.find('.empty-hint').exists()).toBe(false)
  })

  it('readonly 模式:显示全部非禁用分组与全部账号,计数为组内总数,无编辑区', () => {
    const w = mountIt({ mode: 'readonly', publishAccountIds: new Set() })
    const names = w.findAll('.group-name').map(n => n.text())
    expect(names).toEqual(['抖音', '快手', '被禁用平台'])
    // 分组计数 = 组内全部账号数
    expect(w.findAll('.group-count').map(c => c.text())).toEqual(['2', '1', '1'])
    // 无删除按钮、无底部账号设置、无空态提示
    expect(w.find('.account-remove').exists()).toBe(false)
    expect(w.find('.add-btn').exists()).toBe(false)
    expect(w.find('.empty-hint').exists()).toBe(false)
  })

  it('黑名单禁用的平台分组被过滤', () => {
    isPlatformDisabled.mockImplementation(k => k === 'blocked')
    const w = mountIt({ mode: 'readonly' })
    const names = w.findAll('.group-name').map(n => n.text())
    expect(names).toEqual(['抖音', '快手'])
  })

  it('展开状态控制账号列表可见性(v-show)', () => {
    const w = mountIt({ publishAccountIds: new Set([1, 2, 3]) })
    const visibles = w.findAll('.group-accounts').map(g => g.isVisible())
    expect(visibles).toEqual([true, false])
  })

  it('选中平台分组带 is-selected 类', () => {
    const w = mountIt({ selectedPlatform: 'douyin', publishAccountIds: new Set([1, 2, 3]) })
    expect(w.findAll('.group-wrap')[0].classes()).toContain('is-selected')
    expect(w.findAll('.group-wrap')[1].classes()).not.toContain('is-selected')
  })

  it('选中账号项带 active 类,状态点按 status 区分 on/off', () => {
    const w = mountIt({ selectedAccountId: 1 })
    const accounts = w.findAll('.account-item')
    expect(accounts[0].classes()).toContain('active')
    expect(accounts[1].classes()).not.toContain('active')
    expect(accounts[0].find('.dot').classes()).toContain('on')
    expect(accounts[1].find('.dot').classes()).toContain('off')
  })

  it('hasAccountOverride 为 true 的账号带 has-override 类并在 edit 模式显示自定义图标', () => {
    const w = mountIt({ hasAccountOverride: vi.fn(id => id === 2) })
    const accounts = w.findAll('.account-item')
    expect(accounts[1].classes()).toContain('has-override')
    expect(accounts[1].find('.override-icon').exists()).toBe(true)
    // readonly 模式不显示自定义图标
    const rw = mountIt({ mode: 'readonly', hasAccountOverride: vi.fn(id => id === 2) })
    expect(rw.findAll('.account-item')[1].find('.override-icon').exists()).toBe(false)
  })

  it('无头像账号使用默认头像,新浪图床头像走代理', () => {
    const w = mountIt()
    const imgs = w.findAll('.account-avatar img')
    expect(imgs[0].attributes('src')).toContain('ui-avatars.com')
    expect(imgs[1].attributes('src')).toContain('/api/image-proxy?url=')
  })

  it('点击分组头发出 toggle-group(组 key)', async () => {
    const w = mountIt({ publishAccountIds: new Set([1, 2, 3]) })
    await w.findAll('.group-header')[1].trigger('click')
    expect(w.emitted('toggle-group')).toEqual([['kuaishou']])
  })

  it('点击账号项发出 select-account(账号,分组)', async () => {
    const w = mountIt()
    await w.findAll('.account-item')[0].trigger('click')
    const [account, group] = w.emitted('select-account')[0]
    expect(account).toMatchObject({ id: 1, name: '账号A' })
    expect(group).toMatchObject({ key: 'douyin' })
  })

  it('点击删除图标发出 remove-account(账号 id),且不触发选中', async () => {
    const w = mountIt()
    await w.findAll('.account-remove')[1].trigger('click')
    expect(w.emitted('remove-account')).toEqual([[2]])
    expect(w.emitted('select-account')).toBeUndefined()
  })

  it('点击底部「+ 账号设置」发出 open-account-dialog', async () => {
    const w = mountIt()
    await w.find('.add-btn').trigger('click')
    expect(w.emitted('open-account-dialog')).toBeTruthy()
  })
})
