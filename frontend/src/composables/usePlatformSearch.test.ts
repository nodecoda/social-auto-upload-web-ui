import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

// 模块级 mock：API 模块与 ElMessage 在测试里短路，避免真实网络/UI
vi.mock('@/api/douyinImage', () => ({
  douyinImageApi: { searchHotspot: vi.fn(), getMixList: vi.fn() },
}))
vi.mock('@/api/jd', () => ({ jdApi: { novelSearch: vi.fn() } }))
vi.mock('@/api/bilibili', () => ({ biliApi: { getCollections: vi.fn() } }))
vi.mock('@/api/weibo', () => ({ weiboApi: { getCollections: vi.fn() } }))
vi.mock('@/api/weixin_gzh', () => ({ weixinGzhApi: { getCollections: vi.fn() } }))
vi.mock('@/api/xiaohongshu', () => ({ xhsApi: { getCollections: vi.fn() } }))
vi.mock('@/api/channels', () => ({
  channelsApi: { getCollections: vi.fn(), getLocations: vi.fn(), searchActivities: vi.fn() },
}))
vi.mock('element-plus', async (importOriginal) => {
  const mod = await importOriginal<typeof import('element-plus')>()
  return { ...mod, ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }
})

import { biliApi } from '@/api/bilibili'
import { channelsApi } from '@/api/channels'
import { douyinImageApi } from '@/api/douyinImage'
import { jdApi } from '@/api/jd'
import { weiboApi } from '@/api/weibo'
import { weixinGzhApi } from '@/api/weixin_gzh'
import { xhsApi } from '@/api/xiaohongshu'
import { ElMessage } from 'element-plus'

import { usePlatformSearch, type PlatformSearchForm } from './usePlatformSearch'

const mocks = {
  searchHotspot: vi.mocked(douyinImageApi.searchHotspot),
  getMixList: vi.mocked(douyinImageApi.getMixList),
  novelSearch: vi.mocked(jdApi.novelSearch),
  biliCollections: vi.mocked(biliApi.getCollections),
  weiboCollections: vi.mocked(weiboApi.getCollections),
  gzhCollections: vi.mocked(weixinGzhApi.getCollections),
  xhsCollections: vi.mocked(xhsApi.getCollections),
  channelsCollections: vi.mocked(channelsApi.getCollections),
  getLocations: vi.mocked(channelsApi.getLocations),
  searchActivities: vi.mocked(channelsApi.searchActivities),
}

function setup() {
  const form = {} as PlatformSearchForm
  const selectedAccountId = ref<number | string | null>(null)
  const accountStore = { accounts: [{ id: 10, platform: '视频号' }] }
  const api = usePlatformSearch({ form, selectedAccountId, accountStore })
  return { form, selectedAccountId, api }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('usePlatformSearch', () => {
  // ---------- 抖音活动/热点 ----------
  it('handleDouyinActivityChange: 载荷对象携带 challenge 话题时写入 tags（受 5 上限约束）', () => {
    const { form, api } = setup()
    form.tags = ['已有']
    // 兼容历史载荷:challenge 话题挂在数组对象上（旧版单活动对象形态）
    const legacy = [{ activity_id: 1 }] as never
    ;(legacy as unknown as { challenge: string[] }).challenge = ['话题A', '话题B', '话题C', '话题D', '话题E', '话题F']
    api.handleDouyinActivityChange(legacy)
    // 已有 1 个 + activityId 0 → 最多再加 4 个
    expect(form.tags).toEqual(['已有', '话题A', '话题B', '话题C', '话题D'])
    // 无 challenge 的新载荷:不写 tags
    api.handleDouyinActivityChange([{ activity_id: 2 }] as never)
    expect(form.tags).toEqual(['已有', '话题A', '话题B', '话题C', '话题D'])
  })

  it('handleDouyinHotspotChange: 选中/清空', () => {
    const { form, api } = setup()
    api.handleDouyinHotspotChange({ word: '热点词' })
    expect(form.hotspotId).toBe('热点词')
    expect(form.hotspotData).toEqual({ word: '热点词' })
    api.handleDouyinHotspotChange(null)
    expect(form.hotspotId).toBe('')
    expect(form.hotspotData).toBeNull()
  })

  it('fetchDouyinHotspots: 调用后端搜索并返回 sentences', async () => {
    const { selectedAccountId, api } = setup()
    selectedAccountId.value = 7
    mocks.searchHotspot.mockResolvedValue({ data: { sentences: [{ word: '热点' }] } } as never)
    const out = await api.fetchDouyinHotspots('热')
    expect(out.list).toEqual([{ word: '热点' }])
    expect(mocks.searchHotspot).toHaveBeenCalledWith('7', '热')
  })

  it('formatHotValue + douyinHotspotFieldMap.desc', () => {
    const { api } = setup()
    expect(api.formatHotValue(0)).toBe('0')
    expect(api.formatHotValue(5000)).toBe('5000')
    expect(api.formatHotValue(15000)).toBe('1.5万')
    const desc = api.douyinHotspotFieldMap.desc as (item: { hot_value?: number }) => string
    expect(desc({ hot_value: 20000 })).toBe('热度 2.0万')
    expect(desc({})).toBe('')
  })

  // ---------- 京东小说 ----------
  it('fetchJdNovels + jdNovelFieldMap.desc', async () => {
    const { api } = setup()
    mocks.novelSearch.mockResolvedValue({ data: { novels: [{ title: '小说A', category: '都市' }] } } as never)
    const out = await api.fetchJdNovels('小')
    expect(out.list).toEqual([{ title: '小说A', category: '都市' }])
    const desc = api.jdNovelFieldMap.desc as (item: { category?: string; read_count?: number }) => string
    expect(desc({ category: '都市', read_count: 1200 })).toBe('都市 | 1200人已读')
    expect(desc({})).toBe('')
  })

  it('handleJdNovelChange: 选中/清空', () => {
    const { form, api } = setup()
    api.handleJdNovelChange({ title: '小说A' })
    expect(form.jdNovel).toBe('小说A')
    expect(form.jdNovelData).toEqual({ title: '小说A' })
    api.handleJdNovelChange(null)
    expect(form.jdNovel).toBe('')
    expect(form.jdNovelData).toBeNull()
  })

  // ---------- 抖音标签/合集(mix) ----------
  it('handleDouyinTagSelect: 选中写 tagType/tagValue 并弹成功提示', () => {
    const { form, api } = setup()
    api.handleDouyinTagSelect({ type: 'poi', name: '标签名', id: 9 })
    expect(form.selectedTag).toEqual({ type: 'poi', name: '标签名', id: 9 })
    expect(form.tagType).toBe('location')
    expect(form.tagValue).toBe('标签名')
    expect(ElMessage.success).toHaveBeenCalledWith('标签已选择: 标签名')
    api.handleDouyinTagSelect(null)
    expect(form.selectedTag).toBeNull()
    expect(form.tagType).toBe('')
    expect(form.tagValue).toBe('')
  })

  it('handleDouyinTagSelect: 无 name 时 tagValue 回退到 id', () => {
    const { form, api } = setup()
    api.handleDouyinTagSelect({ type: 'game', name: '', id: 3 })
    expect(form.tagType).toBe('gamepad')
    expect(form.tagValue).toBe('3')
  })

  it('handleDouyinMixChange: 选中/清空', () => {
    const { form, api } = setup()
    api.handleDouyinMixChange({ mix_name: '合集1' })
    expect(form.mixId).toBe('合集1')
    expect(form.mixData).toEqual({ mix_name: '合集1' })
    api.handleDouyinMixChange(null)
    expect(form.mixId).toBe('')
    expect(form.mixData).toBeNull()
  })

  // ---------- 合集数据源（前端过滤模式） ----------
  it('fetchBiliCollections: 按关键词过滤', async () => {
    const { api } = setup()
    mocks.biliCollections.mockResolvedValue({ data: { list: [{ name: 'B站合集' }, { name: '其他' }] } } as never)
    const all = await api.fetchBiliCollections('')
    expect(all.list).toHaveLength(2)
    const filtered = await api.fetchBiliCollections('B站')
    expect(filtered.list).toEqual([{ name: 'B站合集' }])
  })

  it('fetchDouyinMixes: 未选账号返回空；有账号按关键词过滤', async () => {
    const { selectedAccountId, api } = setup()
    expect((await api.fetchDouyinMixes('x')).list).toEqual([])
    selectedAccountId.value = 5
    mocks.getMixList.mockResolvedValue({ data: { mix_list: [{ mix_name: '抖音合集' }, { mix_name: '其他' }] } } as never)
    expect((await api.fetchDouyinMixes('抖音')).list).toEqual([{ mix_name: '抖音合集' }])
    expect(mocks.getMixList).toHaveBeenCalledWith(5)
  })

  it('fetchWeiboCollections / fetchGzhCollections / fetchXhsCollections: 关键词过滤 + 选择回调', async () => {
    const { form, api } = setup()
    mocks.weiboCollections.mockResolvedValue({ data: { list: [{ name: '微博合集' }] } } as never)
    expect((await api.fetchWeiboCollections('微博')).list).toEqual([{ name: '微博合集' }])
    api.handleWeiboCollectionChange({ id: 1 })
    expect(form.weiboCollectionData).toEqual({ id: 1 })
    api.handleWeiboCollectionChange(null)
    expect(form.weiboCollectionData).toBeNull()

    mocks.gzhCollections.mockResolvedValue({ data: { list: [{ name: '公众号合集' }] } } as never)
    expect((await api.fetchGzhCollections('公众号')).list).toEqual([{ name: '公众号合集' }])
    api.handleGzhCollectionChange({ id: 2 })
    expect(form.gzhCollectionData).toEqual({ id: 2 })
    api.handleGzhCollectionChange(null)
    expect(form.gzhCollectionData).toBeNull()

    mocks.xhsCollections.mockResolvedValue({ data: { list: [{ id: 'c1', name: '小红书合集', note_num: 3 }] } } as never)
    expect((await api.fetchXhsCollections('小红书')).list).toEqual([{ id: 'c1', name: '小红书合集', note_num: 3 }])
    api.handleXhsCollectionChange({ id: 'c1', name: '小红书合集' })
    expect(form.collectionId).toBe('c1')
    expect(form.collectionData).toEqual({ id: 'c1', name: '小红书合集' })
    api.handleXhsCollectionChange(null)
    expect(form.collectionId).toBe('')
    expect(form.collectionData).toBeNull()
  })

  it('xhsCollectionFieldMap.desc: note_num 有/无', () => {
    const { api } = setup()
    const desc = api.xhsCollectionFieldMap.desc as (item: { note_num?: number }) => string
    expect(desc({ note_num: 0 })).toBe('暂无内容')
    expect(desc({ note_num: 5 })).toBe('共 5 篇')
    expect(desc({})).toBe('')
  })

  // ---------- B站/视频号合集、位置、活动 ----------
  it('B站/视频号合集选择回调', () => {
    const { form, api } = setup()
    api.handleBiliCollectionChange({ id: 'b1' })
    expect(form.biliCollectionData).toEqual({ id: 'b1' })
    api.handleBiliCollectionChange(null)
    expect(form.biliCollectionData).toBeNull()
    api.handleChannelsCollectionChange({ id: 'ch1' })
    expect(form.channelsCollectionData).toEqual({ id: 'ch1' })
    api.handleChannelsCollectionChange(null)
    expect(form.channelsCollectionData).toBeNull()
  })

  it('fetchChannelsCollections: 前端过滤', async () => {
    const { api } = setup()
    mocks.channelsCollections.mockResolvedValue({ data: { list: [{ name: '视频号合集' }, { name: '另一个' }] } } as never)
    expect((await api.fetchChannelsCollections('视频号')).list).toEqual([{ name: '视频号合集' }])
  })

  it('fetchChannelsLocations + 位置选择回调', async () => {
    const { form, api } = setup()
    mocks.getLocations.mockResolvedValue({ data: { list: [{ name: '北京' }] } } as never)
    expect((await api.fetchChannelsLocations('北')).list).toEqual([{ name: '北京' }])
    api.handleChannelsLocationChange({ name: '北京' })
    expect(form.channelsLocationData).toEqual({ name: '北京' })
    api.handleChannelsLocationChange(null)
    expect(form.channelsLocationData).toBeNull()
  })

  it('fetchChannelsActivities: 未选账号退回平台第一个账号的 cookie', async () => {
    const { selectedAccountId, api } = setup()
    mocks.searchActivities.mockResolvedValue({ data: { list: [{ activity_id: 'a1' }] } } as never)
    // 未选账号 → 用 accountStore 兜底 id=10
    await api.fetchChannelsActivities('活动')
    expect(mocks.searchActivities).toHaveBeenCalledWith(10, '活动')
    // 已选账号优先
    selectedAccountId.value = 42
    await api.fetchChannelsActivities('活动')
    expect(mocks.searchActivities).toHaveBeenCalledWith(42, '活动')
  })

  it('channelsActivityFieldMap.desc + 活动选择回调', () => {
    const { form, api } = setup()
    const desc = api.channelsActivityFieldMap.desc as (item: { creator_name?: string }) => string
    expect(desc({ creator_name: '发起人甲' })).toBe('发起人: 发起人甲')
    expect(desc({})).toBe('')
    api.handleChannelsActivityChange({ activity_id: 'a1' })
    expect(form.channelsActivityData).toEqual({ activity_id: 'a1' })
    api.handleChannelsActivityChange(null)
    expect(form.channelsActivityData).toBeNull()
  })
})
