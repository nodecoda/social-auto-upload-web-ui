import { describe, it, expect } from 'vitest'
import { useBatchSetApply } from './useBatchSetApply'

// xiaohongshu key → name '小红书' (来自 @/config/platforms 真实注册表)
function setup() {
  const refs = {
    platformConfigs: {} as Record<string, Record<string, unknown>>,
    accountOverrides: {} as Record<string | number, Record<string, unknown>>,
    accountChecked: {} as Record<string | number, boolean>,
    accountStore: {
      accounts: [
        { id: 1, platform: '小红书' },
        { id: 2, platform: '小红书' },
        { id: 3, platform: '抖音' },
      ],
    },
  }
  const { applyBatchSet } = useBatchSetApply(refs)
  return { ...refs, applyBatchSet }
}

describe('useBatchSetApply', () => {
  const fullPayload = { title: '标题', description: '描述', tags: ['a', 'b'], scheduleTime: '2026-09-01 10:00:00' }

  it('full 模式: 渠道级 + 该渠道所有账号级都写入', () => {
    const { platformConfigs, accountOverrides, applyBatchSet } = setup()
    applyBatchSet(['xiaohongshu'], fullPayload)
    expect(platformConfigs.xiaohongshu).toEqual(fullPayload)
    expect(accountOverrides[1]).toEqual(fullPayload)
    expect(accountOverrides[2]).toEqual(fullPayload)
    // 非该渠道的账号(抖音)不受影响
    expect(accountOverrides[3]).toBeUndefined()
  })

  it('full 模式: tags 使用副本, 后续修改 payload 不影响已写入值', () => {
    const { platformConfigs, accountOverrides, applyBatchSet } = setup()
    const payload = { ...fullPayload }
    applyBatchSet(['xiaohongshu'], payload)
    payload.tags.push('c')
    expect(platformConfigs.xiaohongshu.tags).toEqual(['a', 'b'])
    expect(accountOverrides[1].tags).toEqual(['a', 'b'])
  })

  it('partial 模式: 仅覆盖已填写字段, 空字段保持原值', () => {
    const { platformConfigs, accountOverrides, applyBatchSet } = setup()
    platformConfigs.xiaohongshu = { title: '旧标题', description: '旧描述', tags: ['old'], scheduleTime: '2026-01-01' }
    accountOverrides[1] = { title: '账号旧标题', tags: ['old-acc'] }
    applyBatchSet(['xiaohongshu'], { title: '新标题', description: '', tags: [], scheduleTime: '', mode: 'partial' })
    expect(platformConfigs.xiaohongshu).toEqual({
      title: '新标题',
      description: '旧描述',
      tags: ['old'],
      scheduleTime: '2026-01-01',
    })
    expect(accountOverrides[1]).toEqual({ title: '新标题', tags: ['old-acc'] })
  })

  it('partial 模式全空字段: 渠道级与账号级都不被覆盖', () => {
    const { platformConfigs, accountOverrides, applyBatchSet } = setup()
    platformConfigs.xiaohongshu = { title: '原值' }
    accountOverrides[1] = { title: '账号原值' }
    applyBatchSet(['xiaohongshu'], { title: '', description: '', tags: [], scheduleTime: '', mode: 'partial' })
    expect(platformConfigs.xiaohongshu).toEqual({ title: '原值' })
    expect(accountOverrides[1]).toEqual({ title: '账号原值' })
  })

  it('partial 模式: 已有 override 就地合并, 保留未涉及字段', () => {
    const { accountOverrides, applyBatchSet } = setup()
    accountOverrides[1] = { title: '旧', description: '保留我', tags: [] }
    applyBatchSet(['xiaohongshu'], { description: '新描述', mode: 'partial' })
    expect(accountOverrides[1]).toEqual({ title: '旧', description: '新描述', tags: [] })
  })

  it('scheduleTime 为空: full 模式写空串, partial 模式跳过', () => {
    const { platformConfigs, applyBatchSet } = setup()
    applyBatchSet(['xiaohongshu'], { title: 't', description: 'd', tags: [], scheduleTime: '' })
    expect(platformConfigs.xiaohongshu.scheduleTime).toBe('')
    const { platformConfigs: pc2, applyBatchSet: apply2 } = setup()
    pc2.xiaohongshu = { scheduleTime: '2026-01-01' }
    apply2(['xiaohongshu'], { title: 't2', scheduleTime: '', mode: 'partial' })
    expect(pc2.xiaohongshu.scheduleTime).toBe('2026-01-01')
  })

  it('未知平台 key: 渠道级仍写入, 账号级跳过', () => {
    const { platformConfigs, accountOverrides, applyBatchSet } = setup()
    applyBatchSet(['not-a-platform'], fullPayload)
    expect(platformConfigs['not-a-platform']).toEqual(fullPayload)
    expect(accountOverrides).toEqual({})
  })

  it('accountStore 无账号/空列表: 渠道级仍写入且不抛错', () => {
    const refs = { platformConfigs: {} as Record<string, Record<string, unknown>>, accountOverrides: {}, accountChecked: {}, accountStore: { accounts: [] } }
    const { applyBatchSet } = useBatchSetApply(refs)
    applyBatchSet(['xiaohongshu'], fullPayload)
    expect(refs.platformConfigs.xiaohongshu).toEqual(fullPayload)
    expect(refs.accountOverrides).toEqual({})
  })

  it('无 mode 时默认 full 模式', () => {
    const { platformConfigs, applyBatchSet } = setup()
    applyBatchSet(['xiaohongshu'], { title: 't' })
    expect(platformConfigs.xiaohongshu).toEqual({ title: 't', description: undefined, tags: [], scheduleTime: '' })
  })

  it('已存在的 platformConfigs[pk] 就地更新, 保留其他字段', () => {
    const { platformConfigs, applyBatchSet } = setup()
    const existing = { title: '旧标题', extraField: 'keep' }
    platformConfigs.xiaohongshu = existing
    applyBatchSet(['xiaohongshu'], { title: '新标题', description: 'd', tags: [], scheduleTime: '' })
    expect(platformConfigs.xiaohongshu).toEqual({ title: '新标题', description: 'd', extraField: 'keep', tags: [], scheduleTime: '' })
    expect(platformConfigs.xiaohongshu).toBe(existing)
  })

  it('多平台批量: 每个平台分别写入自己的渠道与账号', () => {
    const { platformConfigs, accountOverrides, applyBatchSet } = setup()
    applyBatchSet(['xiaohongshu', 'douyin'], fullPayload)
    expect(platformConfigs.douyin).toEqual(fullPayload)
    expect(accountOverrides[3]).toEqual(fullPayload)  // 抖音账号
    expect(accountOverrides[1]).toEqual(fullPayload)  // 小红书账号
  })
})
