import { describe, it, expect } from 'vitest'
import {
  getPlatformClass,
  getPlatformColor,
  getPlatformLetter,
  getStatusClass,
  formatStat,
  sortStats,
  getVisibleCount,
  getVisibleStats,
  getExtraStats,
  type StatItem,
} from './accountCardShared'

describe('accountCardShared.getPlatformClass', () => {
  it('已知平台返回 css class', () => {
    expect(getPlatformClass('抖音')).toBeTruthy()
  })

  it('未知平台返回空串', () => {
    expect(getPlatformClass('不存在')).toBe('')
  })
})

describe('accountCardShared.getPlatformColor', () => {
  it('已知平台返回品牌色', () => {
    expect(getPlatformColor('抖音')).toMatch(/^#/)
  })

  it('未知/空平台回退默认紫', () => {
    expect(getPlatformColor(null)).toBe('#8b5cf6')
    expect(getPlatformColor('不存在')).toBe('#8b5cf6')
  })
})

describe('accountCardShared.getPlatformLetter', () => {
  it('未知平台取首字符兜底', () => {
    expect(getPlatformLetter('火星平台')).toBe('火')
  })

  it('空平台回退问号', () => {
    expect(getPlatformLetter(null)).toBe('?')
  })
})

describe('accountCardShared.getStatusClass', () => {
  it('验证中→pending, 正常→normal, 其余→error', () => {
    expect(getStatusClass('验证中')).toBe('pending')
    expect(getStatusClass('正常')).toBe('normal')
    expect(getStatusClass('异常')).toBe('error')
    expect(getStatusClass('未知')).toBe('error')
  })
})

describe('accountCardShared.formatStat', () => {
  it('小于 1000 原样输出', () => {
    expect(formatStat(0)).toBe('0')
    expect(formatStat(999)).toBe('999')
  })

  it('千位用 k', () => {
    expect(formatStat(1000)).toBe('1k')
    expect(formatStat(1234)).toBe('1.2k')
  })

  it('万位用 w', () => {
    expect(formatStat(10000)).toBe('1.0w')
    expect(formatStat(12345)).toBe('1.2w')
    expect(formatStat(123456)).toBe('12.3w')
  })

  it('亿位用 亿', () => {
    expect(formatStat(100000000)).toBe('1.0亿')
    expect(formatStat(123456789)).toBe('1.2亿')
  })

  it('空值/非数字回退 0', () => {
    expect(formatStat(undefined)).toBe('0')
  })
})

describe('accountCardShared.sortStats', () => {
  const stats = [
    { ICON: 'play', COUNT: 100, NAME: '播放', SORT: 2 },
    { ICON: 'like', COUNT: 50, NAME: '点赞', SORT: 1 },
    { ICON: 'star', COUNT: 10, NAME: '收藏' },
  ]

  it('按 SORT 升序,缺失排最后', () => {
    const sorted = sortStats(stats)
    expect(sorted.map(s => s.NAME)).toEqual(['点赞', '播放', '收藏'])
  })

  it('非数组返回空数组', () => {
    expect(sortStats(null)).toEqual([])
    expect(sortStats('x')).toEqual([])
  })
})

describe('accountCardShared.getVisibleCount', () => {
  it('高占用平台返回 3,其余默认 4', () => {
    expect(getVisibleCount({ platform: 'B站' })).toBe(3)
    expect(getVisibleCount({ platform: '抖音' })).toBe(4)
  })
})

describe('accountCardShared.getVisibleStats / getExtraStats', () => {
  const stats: StatItem[] = [
    { ICON: 'a', COUNT: 1, NAME: 'A', SORT: 1 },
    { ICON: 'b', COUNT: 2, NAME: 'B', SORT: 2 },
    { ICON: 'c', COUNT: 3, NAME: 'C', SORT: 3 },
    { ICON: 'd', COUNT: 4, NAME: 'D', SORT: 4 },
  ]

  it('visible 取排序后前 N 项', () => {
    expect(getVisibleStats({ platform: 'B站', stats }).map(s => s.NAME)).toEqual(['A', 'B', 'C'])
    expect(getVisibleStats({ platform: '抖音', stats }).map(s => s.NAME)).toEqual(['A', 'B', 'C', 'D'])
  })

  it('extra 返回全部排序后 stats', () => {
    expect(getExtraStats({ stats }).map(s => s.NAME)).toEqual(['A', 'B', 'C', 'D'])
  })

  it('stats 缺失时返回空数组', () => {
    expect(getVisibleStats({ platform: '抖音', stats: null })).toEqual([])
  })
})
