import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAccountStore } from './account'
import { accountApi } from '@/api/account'

vi.mock('@/api/account', () => ({
  accountApi: {
    getTags: vi.fn(),
  },
}))

describe('useAccountStore', () => {
  let store: any

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useAccountStore()
    vi.clearAllMocks()
  })

  // 后端 SELECT * 行: [id, type, filePath, userName, status, avatar, fans, likes, follows, stats, tags]
  const makeRow = (over: any = {}) => [
    over.id ?? 1,
    over.type ?? 2,          // 视频号 id=2
    over.filePath ?? '/path/1.jpg',
    over.name ?? '测试号',
    over.status ?? 1,
    over.avatar ?? 'avatar.png',
    over.fans ?? 100,
    over.likes ?? 10,
    over.follows ?? 5,
    over.stats ?? '[{"name":"A"}]',
    over.tags ?? ['tag1'],
  ]

  it('初始状态: accounts 与 allTags 为空', () => {
    expect(store.accounts).toEqual([])
    expect(store.allTags).toEqual([])
  })

  it('setAccounts 把后端行数组映射为对象', () => {
    store.setAccounts([makeRow()])
    expect(store.accounts).toHaveLength(1)
    const acc = store.accounts[0]
    expect(acc.id).toBe(1)
    expect(acc.name).toBe('测试号')
    expect(acc.filePath).toBe('/path/1.jpg')
    expect(acc.avatar).toBe('avatar.png')
    expect(acc.fans).toBe(100)
    expect(acc.likes).toBe(10)
    expect(acc.follows).toBe(5)
    expect(acc.tags).toEqual(['tag1'])
  })

  it('setAccounts 映射 status: -1→验证中 / 1→正常 / 其他→异常', () => {
    store.setAccounts([
      makeRow({ id: 1, status: -1 }),
      makeRow({ id: 2, status: 1 }),
      makeRow({ id: 3, status: 0 }),
    ])
    expect(store.accounts.map((a: any) => a.status)).toEqual(['验证中', '正常', '异常'])
  })

  it('setAccounts 映射 platform: 按 platformIdToName, 未知 id 为 未知', () => {
    store.setAccounts([makeRow({ type: 2 }), makeRow({ id: 2, type: 99 })])
    expect(store.accounts[0].platform).toBe('视频号')
    expect(store.accounts[1].platform).toBe('未知')
  })

  it('setAccounts 解析 stats JSON 字符串为数组', () => {
    store.setAccounts([makeRow()])
    expect(store.accounts[0].stats).toEqual([{ name: 'A' }])
  })

  it('setAccounts 对非法 JSON stats 回退为空数组, 数组 stats 直接使用', () => {
    store.setAccounts([makeRow({ stats: 'not-json' }), makeRow({ id: 2, stats: [{ name: 'B' }] })])
    expect(store.accounts[0].stats).toEqual([])
    expect(store.accounts[1].stats).toEqual([{ name: 'B' }])
  })

  it('setAccounts 缺省 tags 时回退为空数组', () => {
    // 只有 10 项且最后一项为空字符串 → item[10] undefined, item[last] 空 → []
    const shortRow = makeRow({ tags: undefined }).slice(0, 10)
    shortRow[9] = ''
    store.setAccounts([shortRow])
    expect(store.accounts[0].tags).toEqual([])
  })

  it('addAccount 追加到列表末尾', () => {
    store.setAccounts([makeRow()])
    store.addAccount({ id: 2, name: '新账号', platform: '小红书' })
    expect(store.accounts).toHaveLength(2)
    expect(store.accounts[1].name).toBe('新账号')
  })

  it('updateAccount 合并更新已有账号字段, 不存在的 id 不影响列表', () => {
    store.setAccounts([makeRow({ id: 1 })])
    store.updateAccount(1, { fans: 999, name: '改名' })
    expect(store.accounts[0].fans).toBe(999)
    expect(store.accounts[0].name).toBe('改名')
    expect(store.accounts[0].id).toBe(1)
    store.updateAccount(42, { fans: 1 })
    expect(store.accounts).toHaveLength(1)
  })

  it('deleteAccount 删除指定 id, 不存在的 id 不改变列表', () => {
    store.setAccounts([makeRow({ id: 1 }), makeRow({ id: 2 })])
    store.deleteAccount(1)
    expect(store.accounts.map((a: any) => a.id)).toEqual([2])
    store.deleteAccount(99)
    expect(store.accounts).toHaveLength(1)
  })

  it('getAccountsByPlatform 按平台名筛选', () => {
    store.setAccounts([
      makeRow({ id: 1, type: 2 }),            // 视频号
      makeRow({ id: 2, type: 2 }),            // 视频号
      makeRow({ id: 3, type: 1 }),            // 小红书
    ])
    const result = store.getAccountsByPlatform('视频号')
    expect(result.map((a: any) => a.id)).toEqual([1, 2])
  })

  it('loadTags 成功时写入 allTags', async () => {
    vi.mocked(accountApi.getTags).mockResolvedValue({ code: 200, data: ['tag-a', 'tag-b'] })
    await store.loadTags()
    expect(store.allTags).toEqual(['tag-a', 'tag-b'])
    expect(accountApi.getTags).toHaveBeenCalledTimes(1)
  })

  it('loadTags 接口失败时 allTags 不变并吞掉错误', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.mocked(accountApi.getTags).mockRejectedValue(new Error('network'))
    await store.loadTags()
    expect(store.allTags).toEqual([])
    expect(consoleSpy).toHaveBeenCalled()
    consoleSpy.mockRestore()
  })

  it('loadTags 返回非 200 时不清空已有标签', async () => {
    store.allTags = ['old']
    vi.mocked(accountApi.getTags).mockResolvedValue({ code: 500, data: [] })
    await store.loadTags()
    expect(store.allTags).toEqual(['old'])
  })
})
