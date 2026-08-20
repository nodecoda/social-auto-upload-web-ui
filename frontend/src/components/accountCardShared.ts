// AccountCard 与 AccountManagement 视图共享的纯函数与类型（F2f）

import { h, type Component } from 'vue'
import { platformCssMap, getPlatformByName } from '@/config/platforms'

/** 账号 stats 条目（后端 stats JSON 数组元素） */
export interface StatItem {
  ICON?: string
  COUNT?: number | string
  NAME?: string
  SORT?: number | string
}

/** 账号标签 */
export interface TagItem {
  id: number | string
  name: string
  color?: string
}

/** 账号条目（accountStore.accounts 的元素） */
export interface AccountItem {
  id: number
  type: number
  filePath: string
  name: string
  status: string
  platform: string
  avatar: string
  fans: number
  likes: number
  follows: number
  stats: StatItem[]
  tags: TagItem[]
}

export const getPlatformClass = (platform: string) => {
  return platformCssMap[platform] || ''
}

export const getPlatformColor = (platform: string | null) => {
  const p = getPlatformByName(platform ?? '')
  return p?.color || '#8b5cf6'
}

export const getPlatformBg = (platform: string | null) => {
  const p = getPlatformByName(platform ?? '')
  return p?.bgColor || 'rgba(139, 92, 246, 0.15)'
}

export const getPlatformLogo = (platform: string | null) => {
  const p = getPlatformByName(platform ?? '')
  return p?.logo || null
}

export const getPlatformLetter = (platform: string | null) => {
  const p = getPlatformByName(platform ?? '')
  return p?.letter || platform?.charAt(0) || '?'
}

export const getStatusClass = (status: string) => {
  if (status === '验证中') return 'pending'
  if (status === '正常') return 'normal'
  return 'error'
}

// 数值格式化:10000 → 1.0w, 12345 → 1.2w, 100000000 → 1.0亿
export const formatStat = (value: number | string | undefined) => {
  const n = Number(value) || 0
  if (n < 1000) return String(n)
  if (n < 10000) return (n / 1000).toFixed(n % 1000 === 0 ? 0 : 1) + 'k'
  if (n < 100000000) {
    const v = n / 10000
    return (v >= 100 ? v.toFixed(0) : v.toFixed(1)) + 'w'
  }
  const v = n / 100000000
  return (v >= 100 ? v.toFixed(0) : v.toFixed(1)) + '亿'
}

// 账号 stats 排序:按 SORT 升序(SORT 缺失时排到最后)
export const sortStats = (stats: unknown): StatItem[] => {
  if (!Array.isArray(stats)) return []
  return [...stats].sort((a, b) => (Number((a as StatItem)?.SORT) || 999) - (Number((b as StatItem)?.SORT) || 999))
}

// 卡片显示的 stats:按 SORT 排序后取前 N 项(N 由平台决定)
// 大多数平台 stats 总数 ≤ 4,正常展示;超过 4 项的平台只展示前 3 项(剩余进悬浮窗)
// 注意 key 用 platform name(中文),与 store 解包后的 account.platform 一致
const VISIBLE_COUNTS: Record<string, number> = {
  'B站': 3,       // 8 项 stats:粉丝 + 点赞 + 收藏 + 更多占位
  '百家号': 3,    // 6 项 stats:粉丝 + 播放量 + 搜索量 + 更多占位
  '腾讯视频': 3,  // 8 项 stats:粉丝 + 总点赞 + 总评论 + 更多占位
  '知乎': 3,      // 9 项 stats:粉丝 + 赞同 + 阅读 + 更多占位
  'CSDN': 3,      // 4 项 stats:粉丝 + 总阅读 + 收藏 + 更多占位
}
export const getVisibleCount = (account: { platform: string }) => {
  return VISIBLE_COUNTS[account?.platform] ?? 4
}

export const getVisibleStats = (account: { platform: string; stats: unknown }): StatItem[] => {
  return sortStats(account?.stats).slice(0, getVisibleCount(account))
}

// "更多"占位需要显示时,展示该账号的**全部** stats(不是剩余),
// 鼠标悬停时能看到完整运营数据
export const getExtraStats = (account: { stats: unknown }): StatItem[] => {
  return sortStats(account?.stats)
}

// "更多"块 hover 时,动态调整浮窗水平位置,避免最右侧卡片溢出视口触发横向滚动条
// 浮窗本身用 left:50% + transform:translateX(-50%) 居中,JS 在 hover 时根据
// 浮窗实际位置算出溢出量,通过 --stats-popover-offset CSS 变量微调 translateX
export const handleStatsHover = (event: MouseEvent) => {
  const trigger = event.currentTarget as HTMLElement | null
  if (!trigger) return
  const popover = trigger.querySelector('.stats-more-popover') as HTMLElement | null
  if (!popover) return

  // 触发块的视口位置
  const triggerRect = trigger.getBoundingClientRect()
  // 浮窗的预期尺寸(先用临时显示拿真实尺寸,或者用默认 min-width 220)
  const popoverWidth = popover.offsetWidth || 220
  // 浮窗居中时左边缘 = 触发块中心 - 浮窗宽度/2
  const centeredLeft = triggerRect.left + triggerRect.width / 2 - popoverWidth / 2
  // 浮窗居中时右边缘
  const centeredRight = centeredLeft + popoverWidth
  // 视口宽度
  const vw = window.innerWidth
  // 安全边距(避免贴边)
  const margin = 8

  let offsetPx = 0
  if (centeredRight > vw - margin) {
    // 右边溢出 → 往左推
    offsetPx = centeredRight - (vw - margin)
  } else if (centeredLeft < margin) {
    // 左边溢出 → 往右推
    offsetPx = -(margin - centeredLeft)
  }
  trigger.style.setProperty('--stats-popover-offset', `${-offsetPx}px`)
}

// ICON 字符串 -> 渲染组件(SVG),通过 h() 创建组件实例(避免每个 ICON 写一个 .vue 文件)
// SVG 风格保持与项目现有统计图标一致(Feather/Lucide 风格,14px stroke)
const ICON_PATHS: Record<string, string> = {
  user:   '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path>',
  like:   '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>',
  follow: '<path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line>',
  play:   '<polygon points="5 3 19 12 5 21 5 3"></polygon>',
  video:  '<polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>',
  star:   '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>',
  coin:   '<circle cx="12" cy="12" r="10"></circle><path d="M9.5 9a2.5 2.5 0 1 1 5 0c0 1.5-2.5 2-2.5 3.5"></path><line x1="12" y1="17" x2="12" y2="17.01"></line>',
  chat:   '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>',
  share:  '<circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>',
  edit:   '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>',
}

// 缓存 h() 组件(避免每次 render 重新创建)
const _iconCache: Record<string, Component> = {}
export const getIconComponent = (iconKey: string): Component => {
  const key = iconKey || 'user'
  if (_iconCache[key]) return _iconCache[key]
  const inner = ICON_PATHS[key] || ICON_PATHS.user
  const comp: Component = {
    name: `StatIcon-${key}`,
    render() {
      return h('svg', {
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': '2',
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        innerHTML: inner,
      })
    },
  }
  _iconCache[key] = comp
  return comp
}
