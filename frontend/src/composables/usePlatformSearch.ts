/**
 * 平台搜索域 composable（PublishCenter 拆分 #9 第 1 片）。
 *
 * 收敛发布面板里所有「RemoteSearchSelect 数据源 + 选择回调 + 字段映射」：
 * 抖音活动/热点/标签/合集(mix)、京东小说、B站/微博/公众号/小红书/视频号合集、
 * 视频号位置/活动。行为与拆分前完全一致（纯搬移，无逻辑改动）。
 *
 * 依赖注入：form（写回选择结果）、selectedAccountId（账号级搜索上下文）、
 * accountStore（视频号活动未选账号时退回平台第一个账号）。
 */
import { ElMessage } from 'element-plus'
import type { Ref } from 'vue'
import { biliApi } from '@/api/bilibili'
import { channelsApi } from '@/api/channels'
import { douyinImageApi } from '@/api/douyinImage'
import { jdApi } from '@/api/jd'
import { weiboApi } from '@/api/weibo'
import { weixinGzhApi } from '@/api/weixin_gzh'
import { xhsApi } from '@/api/xiaohongshu'
import type { ApiResponse } from '@/utils/request'

// ========== 类型 ==========

/** 抖音标签（DouyinTagSelect change 载荷） */
export interface DouyinTag {
  type: string
  name: string
  id?: string | number
  _searchKeyword?: string
  [key: string]: unknown
}

/** 抖音热点搜索条目 */
interface HotspotItem {
  word?: string
  hot_value?: number
  [key: string]: unknown
}

/** 京东小说条目 */
interface JdNovelItem {
  title?: string
  category?: string
  read_count?: number
  image?: string
  [key: string]: unknown
}

/** 小红书合集条目 */
interface XhsCollectionItem {
  id?: string | number
  name?: string
  note_num?: number
  [key: string]: unknown
}

/** 视频号活动条目 */
interface ChannelsActivityItem {
  activity_id?: string
  name?: string
  creator_name?: string
  [key: string]: unknown
}

/** 各 Select 组件 change 载荷的窄接口(仅声明本面板用到的字段) */
interface ActivityItemPayload {
  activity_id?: string | number
  activity_name?: string
  [key: string]: unknown
}

/** 搜索域写回表单的最小字段面（FormState 的子集） */
export interface PlatformSearchForm {
  tags?: string[]
  activityId?: string[]
  hotspotId?: string
  hotspotData?: Record<string, unknown> | null
  selectedTag?: DouyinTag | null
  tagType?: string
  tagValue?: string
  mixId?: string
  mixData?: Record<string, unknown> | null
  collectionId?: string | number
  collectionData?: Record<string, unknown> | null
  biliCollectionData?: Record<string, unknown> | null
  channelsCollectionData?: Record<string, unknown> | null
  channelsLocationData?: Record<string, unknown> | null
  channelsActivityData?: Record<string, unknown> | null
  weiboCollectionData?: Record<string, unknown> | null
  gzhCollectionData?: Record<string, unknown> | null
  jdNovel?: string
  jdNovelData?: Record<string, unknown> | null
}

/** 账号仓库的最小访问面（仅视频号活动搜索兜底用） */
interface AccountStoreLike {
  accounts: Array<{ platform?: string; id?: number | string }>
}

export function usePlatformSearch(options: {
  form: PlatformSearchForm
  selectedAccountId: Ref<number | string | null>
  accountStore: AccountStoreLike
}) {
  const { form, selectedAccountId, accountStore } = options

  // ========== Douyin-specific Methods ==========

  function handleDouyinActivityChange(activity: ActivityItemPayload[]) {
    // 兼容历史载荷:旧版单活动对象携带 challenge 话题数组(现 change 载荷为活动数组,该分支实际不触发)
    const topics = (activity as unknown as { challenge?: string[] } | null)?.challenge
    if (topics && topics.length > 0) {
      for (const topic of topics) {
        if (form.tags && !form.tags.includes(topic)) {
          if ((form.activityId?.length || 0) + (form.tags?.length || 0) >= 5) break
          form.tags.push(topic)
        }
      }
    }
  }

  function handleDouyinHotspotChange(hotspot: Record<string, unknown> | null) {
    if (hotspot) {
      form.hotspotId = hotspot.word as string | undefined
      form.hotspotData = hotspot
    } else {
      form.hotspotId = ''
      form.hotspotData = null
    }
  }

  // 抖音关联热点 —— RemoteSearchSelect 数据源(后端搜索模式,必须传 keyword)
  async function fetchDouyinHotspots(keyword: string) {
    const resp = (await douyinImageApi.searchHotspot(String(selectedAccountId.value || ''), keyword || '')) as ApiResponse<{ sentences?: unknown[] }>
    return { list: resp.data?.sentences || [] }
  }
  // 热点字段映射:word 标题,hot_value 派生热度文案,word_cover.url_list.0 嵌套封面
  const douyinHotspotFieldMap: Record<string, string | ((item: HotspotItem) => string)> = {
    label: 'word',
    key: 'sentence_id',
    desc: (item) => item.hot_value ? `热度 ${formatHotValue(item.hot_value)}` : '',
    cover: 'word_cover.url_list.0'
  }
  function formatHotValue(value: number) {
    if (!value) return '0'
    return value >= 10000 ? (value / 10000).toFixed(1) + '万' : String(value)
  }

  // 京东小说 —— RemoteSearchSelect 数据源(后端搜索模式,必须传 keyword)
  async function fetchJdNovels(keyword: string) {
    const resp = (await jdApi.novelSearch(String(selectedAccountId.value || ''), keyword || '')) as ApiResponse<{ novels?: unknown[] }>
    return { list: resp.data?.novels || [] }
  }
  // 小说字段映射:title 书名(做 modelValue label),image 封面,desc 由分类+阅读人数拼出
  const jdNovelFieldMap: Record<string, string | ((item: JdNovelItem) => string)> = {
    label: 'title',
    key: 'title',
    desc: (item) => [item.category, item.read_count ? `${item.read_count}人已读` : ''].filter((s): s is string => Boolean(s)).join(' | '),
    cover: 'image'
  }
  function handleJdNovelChange(novel: Record<string, unknown> | null) {
    if (novel) {
      form.jdNovel = novel.title as string | undefined
      form.jdNovelData = novel
    } else {
      form.jdNovel = ''
      form.jdNovelData = null
    }
  }

  function handleDouyinTagSelect(tag: DouyinTag | null) {
    if (tag) {
      form.selectedTag = tag
      const m: Record<string, string> = { poi: 'location', miniapp: 'miniapp', game: 'gamepad', mark: 'mark', film: 'film' }
      form.tagType = m[tag.type ?? ''] || ''
      form.tagValue = tag.name || (tag.id ? String(tag.id) : '')
      ElMessage.success(`标签已选择: ${tag.name}`)
    } else {
      form.selectedTag = null
      form.tagType = ''
      form.tagValue = ''
    }
  }

  function handleDouyinMixChange(mix: Record<string, unknown> | null) {
    if (mix) {
      form.mixId = mix.mix_name as string | undefined
      form.mixData = mix
    } else {
      form.mixId = ''
      form.mixData = null
    }
  }

  // B站合集 —— RemoteSearchSelect 数据源(前端过滤模式)
  async function fetchBiliCollections(keyword: string) {
    const resp = (await biliApi.getCollections(selectedAccountId.value)) as ApiResponse<{ list?: Array<{ name?: string }> }>
    const all = resp.data?.list || []
    const kw = keyword?.trim().toLowerCase()
    return {
      list: kw ? all.filter(c => c.name?.toLowerCase().includes(kw)) : all
    }
  }

  // 抖音合集(mix)—— RemoteSearchSelect 数据源(前端过滤模式,空关键词清空)
  async function fetchDouyinMixes(keyword: string) {
    const accountId = selectedAccountId.value
    if (accountId === null) return { list: [] }
    const resp = (await douyinImageApi.getMixList(accountId)) as ApiResponse<{ mix_list?: Array<{ mix_name?: string }> }>
    const all = resp.data?.mix_list || []
    const kw = keyword?.trim().toLowerCase()
    return {
      list: kw ? all.filter(m => m.mix_name?.toLowerCase().includes(kw)) : all
    }
  }

  // 微博合集 —— RemoteSearchSelect 数据源(后端一次返回全量,前端过滤)
  async function fetchWeiboCollections(keyword: string) {
    const resp = (await weiboApi.getCollections(selectedAccountId.value)) as ApiResponse<{ list?: Array<{ name?: string }> }>
    const all = resp.data?.list || []
    const kw = keyword?.trim().toLowerCase()
    return {
      list: kw ? all.filter(c => c.name?.toLowerCase().includes(kw)) : all
    }
  }

  // 微博合集选择回调
  function handleWeiboCollectionChange(col: Record<string, unknown> | null) {
    if (col) {
      form.weiboCollectionData = col
    } else {
      form.weiboCollectionData = null
    }
  }

  // 微信公众号合集 —— RemoteSearchSelect 数据源(后端一次返回全量,前端过滤)
  async function fetchGzhCollections(keyword: string) {
    const resp = (await weixinGzhApi.getCollections(selectedAccountId.value)) as ApiResponse<{ list?: Array<{ name?: string }> }>
    const all = resp.data?.list || []
    const kw = keyword?.trim().toLowerCase()
    return {
      list: kw ? all.filter(c => c.name?.toLowerCase().includes(kw)) : all
    }
  }

  // 微信公众号合集选择回调
  function handleGzhCollectionChange(col: Record<string, unknown> | null) {
    if (col) {
      form.gzhCollectionData = col
    } else {
      form.gzhCollectionData = null
    }
  }

  // 小红书合集选择回调:v-model 已把 collectionName 绑到 form.collectionName,
  // 这里把完整对象(含 id)存到 form.collectionData,并把 id 同步到 form.collectionId
  function handleXhsCollectionChange(col: { id?: string | number; [key: string]: unknown } | null) {
    if (col) {
      form.collectionId = col.id || ''
      form.collectionData = col
    } else {
      form.collectionId = ''
      form.collectionData = null
    }
  }

  // 小红书合集 —— RemoteSearchSelect 数据源与字段映射
  // 后端一次返回全量合集,前端按关键词过滤(searchMode=frontend + load-all)
  async function fetchXhsCollections(keyword: string) {
    const resp = (await xhsApi.getCollections(selectedAccountId.value)) as ApiResponse<{ list?: Array<{ name?: string }> }>
    const all = resp.data?.list || []
    const kw = keyword?.trim().toLowerCase()
    return {
      list: kw ? all.filter(c => c.name?.toLowerCase().includes(kw)) : all
    }
  }
  const xhsCollectionFieldMap: Record<string, string | ((item: XhsCollectionItem) => string)> = {
    label: 'name',
    key: 'id',
    desc: (item) => item.note_num != null
      ? (item.note_num > 0 ? `共 ${item.note_num} 篇` : '暂无内容')
      : ''
  }

  // B 站合集选择回调:v-model 已把 biliCollectionName 绑到 form,
  // 这里把完整对象存到 form.biliCollectionData
  function handleBiliCollectionChange(col: Record<string, unknown> | null) {
    if (col) {
      form.biliCollectionData = col
    } else {
      form.biliCollectionData = null
    }
  }

  // 视频号合集选择回调
  function handleChannelsCollectionChange(col: Record<string, unknown> | null) {
    if (col) {
      form.channelsCollectionData = col
    } else {
      form.channelsCollectionData = null
    }
  }

  // 视频号位置选择回调
  function handleChannelsLocationChange(loc: Record<string, unknown> | null) {
    if (loc) {
      form.channelsLocationData = loc
    } else {
      form.channelsLocationData = null
    }
  }

  // 视频号合集 —— RemoteSearchSelect 数据源(前端过滤模式,后端一次返回全量)
  async function fetchChannelsCollections(keyword: string) {
    const resp = (await channelsApi.getCollections(selectedAccountId.value)) as ApiResponse<{ list?: Array<{ name?: string }> }>
    const all = resp.data?.list || []
    const kw = keyword?.trim().toLowerCase()
    return {
      list: kw ? all.filter(c => c.name?.toLowerCase().includes(kw)) : all
    }
  }

  // 视频号位置 —— RemoteSearchSelect 数据源(后端搜索模式,必须传 keyword)
  async function fetchChannelsLocations(keyword: string) {
    const resp = (await channelsApi.getLocations(selectedAccountId.value, keyword || '')) as ApiResponse<{ list?: unknown[] }>
    return { list: resp.data?.list || [] }
  }

  // 视频号活动 —— RemoteSearchSelect 数据源(后端搜索模式,必须传 keyword)
  // DOM: option-item 内 .creator-name(发起人)+ .name(活动名) 两个 span,
  // label 拼成「creator-name + 空格 + name」,desc 单放 .name(后端已分好)
  async function fetchChannelsActivities(keyword: string) {
    // 活动是平台级字段:未选账号时退回到该平台第一个账号的 cookie 去搜
    const aid = selectedAccountId.value
      || accountStore.accounts.find(a => a.platform === '视频号')?.id
      || ''
    const resp = (await channelsApi.searchActivities(aid, keyword || '')) as ApiResponse<{ list?: unknown[] }>
    return { list: resp.data?.list || [] }
  }
  const channelsActivityFieldMap: Record<string, string | ((item: ChannelsActivityItem) => string)> = {
    key: 'activity_id',
    label: 'name',
    desc: (item) => item.creator_name ? `发起人: ${item.creator_name}` : ''
  }

  // 视频号活动选择回调:存完整对象到 form.channelsActivityData
  function handleChannelsActivityChange(act: Record<string, unknown> | null) {
    if (act) {
      form.channelsActivityData = act
    } else {
      form.channelsActivityData = null
    }
  }

  return {
    handleDouyinActivityChange,
    handleDouyinHotspotChange,
    fetchDouyinHotspots,
    douyinHotspotFieldMap,
    formatHotValue,
    fetchJdNovels,
    jdNovelFieldMap,
    handleJdNovelChange,
    handleDouyinTagSelect,
    handleDouyinMixChange,
    fetchBiliCollections,
    fetchDouyinMixes,
    fetchWeiboCollections,
    handleWeiboCollectionChange,
    fetchGzhCollections,
    handleGzhCollectionChange,
    fetchXhsCollections,
    xhsCollectionFieldMap,
    handleXhsCollectionChange,
    handleBiliCollectionChange,
    handleChannelsCollectionChange,
    handleChannelsLocationChange,
    fetchChannelsCollections,
    fetchChannelsLocations,
    fetchChannelsActivities,
    channelsActivityFieldMap,
    handleChannelsActivityChange,
  }
}
