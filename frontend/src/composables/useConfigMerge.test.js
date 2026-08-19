import { describe, it, expect } from 'vitest'
import { mergeConfig } from './useConfigMerge'

describe('mergeConfig 4 级优先级合并（accountOv > platformOv > platformDefault > common）', () => {
  const common = { title: '公共标题', coverLandscape: 'common-land.jpg', videoPortrait: 'common-port.mp4' }
  const platformDefault = { title: '平台默认', tags: ['平台标签'], scheduleTime: '2026-08-20 10:00:00' }
  const platformOv = { title: '渠道覆盖', tags: ['渠道标签'] }
  const accountOv = { title: '账号覆盖' }

  it('文本字段：账号 > 渠道 > 平台默认 > 公共', () => {
    const m = mergeConfig(common, platformDefault, platformOv, accountOv)
    expect(m.title).toBe('账号覆盖')
    expect(mergeConfig(common, platformDefault, platformOv, null).title).toBe('渠道覆盖')
    expect(mergeConfig(common, platformDefault, null, null).title).toBe('平台默认')
    expect(mergeConfig(common, null, null, null).title).toBe('')
  })

  it('tags 数组走 4 级合并', () => {
    const m = mergeConfig(common, platformDefault, platformOv, null)
    expect(m.tags).toEqual(['渠道标签'])
    expect(mergeConfig(common, platformDefault, null, null).tags).toEqual(['平台标签'])
    expect(mergeConfig(common, null, null, null).tags).toEqual([])
  })

  it('封面/视频素材：4 级合并后兜底 common', () => {
    const m = mergeConfig(common, null, null, null)
    expect(m.coverLandscape).toBe('common-land.jpg')
    expect(m.videoPortrait).toBe('common-port.mp4')
  })

  it('scheduleTime：账号级显式设置（含清空）优先于平台默认', () => {
    // 账号级显式 null（清空定时）→ 结果空串，不 fallback 平台默认
    const m = mergeConfig(common, platformDefault, null, { scheduleTime: null })
    expect(m.scheduleTime).toBe('')
    // 账号级显式时间 → 用账号级
    const m2 = mergeConfig(common, platformDefault, null, { scheduleTime: '2026-09-01 09:00:00' })
    expect(m2.scheduleTime).toBe('2026-09-01 09:00:00')
    // 账号未操作过 → 用平台默认
    const m3 = mergeConfig(common, platformDefault, null, null)
    expect(m3.scheduleTime).toBe('2026-08-20 10:00:00')
    // 平台级显式清空 → 空
    const m4 = mergeConfig(common, platformDefault, { scheduleTime: '' }, null)
    expect(m4.scheduleTime).toBe('')
  })

  it('布尔/数字字段带默认值', () => {
    const m = mergeConfig(common, platformDefault, null, null)
    expect(m.isOriginal).toBe(false)
    expect(m.enableTimer).toBe(0)
  })

  it('平台特有字段穿透（京东/抖音等）', () => {
    const m = mergeConfig(common, { jdDeclaration: '声明' }, null, null)
    expect(m.jdDeclaration).toBe('声明')
    expect(mergeConfig(common, null, null, null).jdDeclaration).toBe(String(""))
  })
})
