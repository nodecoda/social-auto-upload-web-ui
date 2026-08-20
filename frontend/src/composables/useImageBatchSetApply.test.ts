import { describe, it, expect, vi } from 'vitest'
import { useImageBatchSetApply } from './useImageBatchSetApply'

// xiaohongshu key → name '小红书' (来自 @/config/platforms 真实注册表)
function setup() {
  const panels: any = {
    xiaohongshu: {
      publicApi: { setPlatformConfig: vi.fn(), setAccountOverride: vi.fn() },
    },
    douyin: {
      setPlatformConfig: vi.fn(), // 方法直接在 panel 上 (defineExpose 展开)
      setAccountOverride: vi.fn(),
    },
    missing: {}, // 无 API 的 panel 应被跳过
  }
  const accountStore = {
    accounts: [
      { id: 1, platform: '小红书' },
      { id: 2, platform: '小红书' },
      { id: 3, platform: '抖音' },
      { id: 4, platform: '抖音' },
    ],
  }
  const { applyImageBatchSet } = useImageBatchSetApply({ panels, accountStore })
  return { panels, accountStore, applyImageBatchSet }
}

const fullPayload = { title: '图集标题', description: '图集描述', tags: ['a', 'b'], scheduleTime: '2026-09-01 10:00:00' }
// full 模式也会写入派生的 enableTimer (scheduleTime 非空 → true)
const fullExpected = { ...fullPayload, enableTimer: true }

describe('useImageBatchSetApply', () => {
  it('full 模式: 渠道级 + 该渠道所有账号级都写入', () => {
    const { panels, applyImageBatchSet } = setup()
    applyImageBatchSet(['xiaohongshu'], fullPayload)
    expect(panels.xiaohongshu.publicApi.setPlatformConfig).toHaveBeenCalledWith(fullExpected)
    expect(panels.xiaohongshu.publicApi.setAccountOverride).toHaveBeenCalledTimes(2)
    expect(panels.xiaohongshu.publicApi.setAccountOverride).toHaveBeenCalledWith(1, fullExpected)
    expect(panels.xiaohongshu.publicApi.setAccountOverride).toHaveBeenCalledWith(2, fullExpected)
  })

  it('platformKey 匹配正确平台名的账号', () => {
    const { panels, applyImageBatchSet } = setup()
    applyImageBatchSet(['douyin'], { title: 't', description: '', tags: [], scheduleTime: '' })
    expect(panels.douyin.setAccountOverride).toHaveBeenCalledTimes(2) // 抖音 2 个账号
    expect(panels.douyin.setAccountOverride).toHaveBeenCalledWith(3, expect.any(Object))
    expect(panels.douyin.setAccountOverride).toHaveBeenCalledWith(4, expect.any(Object))
    // xiaohongshu 未被触及
    expect(panels.xiaohongshu.publicApi.setPlatformConfig).not.toHaveBeenCalled()
  })

  it('partial 模式: 只写入已填字段, 空字段不传', () => {
    const { panels, applyImageBatchSet } = setup()
    applyImageBatchSet(['xiaohongshu'], { title: '只有标题', description: '', tags: [], scheduleTime: '', mode: 'partial' })
    expect(panels.xiaohongshu.publicApi.setPlatformConfig).toHaveBeenCalledWith({ title: '只有标题' })
  })

  it('partial 模式: 全部字段为空时跳过该渠道', () => {
    const { panels, applyImageBatchSet } = setup()
    applyImageBatchSet(['xiaohongshu'], { title: '', description: '', tags: [], scheduleTime: '', mode: 'partial' })
    expect(panels.xiaohongshu.publicApi.setPlatformConfig).not.toHaveBeenCalled()
    expect(panels.xiaohongshu.publicApi.setAccountOverride).not.toHaveBeenCalled()
  })

  it('scheduleTime 非空时 enableTimer 派生为 true', () => {
    const { panels, applyImageBatchSet } = setup()
    applyImageBatchSet(['xiaohongshu'], { title: 't', description: 'd', tags: [], scheduleTime: '2026-09-01 10:00:00' })
    const fields = panels.xiaohongshu.publicApi.setPlatformConfig.mock.calls[0][0]
    expect(fields.enableTimer).toBe(true)
  })

  it('scheduleTime 留空时 enableTimer 派生为 false', () => {
    const { panels, applyImageBatchSet } = setup()
    applyImageBatchSet(['xiaohongshu'], { title: 't', description: 'd', tags: [], scheduleTime: '' })
    const fields = panels.xiaohongshu.publicApi.setPlatformConfig.mock.calls[0][0]
    expect(fields.enableTimer).toBe(false)
  })

  it('tags 拷贝隔离: 不修改调用方数组', () => {
    const { panels, applyImageBatchSet } = setup()
    const tags = ['x']
    applyImageBatchSet(['xiaohongshu'], { title: 't', description: 'd', tags, scheduleTime: '' })
    tags.push('y')
    const fields = panels.xiaohongshu.publicApi.setPlatformConfig.mock.calls[0][0]
    expect(fields.tags).toEqual(['x'])
  })

  it('无 setPlatformConfig 的 panel 被跳过 (不抛错)', () => {
    const { panels, applyImageBatchSet } = setup()
    expect(() => applyImageBatchSet(['missing'], fullPayload)).not.toThrow()
  })

  it('多平台批量: 各渠道独立写入', () => {
    const { panels, applyImageBatchSet } = setup()
    applyImageBatchSet(['xiaohongshu', 'douyin'], fullPayload)
    expect(panels.xiaohongshu.publicApi.setPlatformConfig).toHaveBeenCalledTimes(1)
    expect(panels.douyin.setPlatformConfig).toHaveBeenCalledTimes(1)
    expect(panels.douyin.setAccountOverride).toHaveBeenCalledTimes(2)
  })
})
