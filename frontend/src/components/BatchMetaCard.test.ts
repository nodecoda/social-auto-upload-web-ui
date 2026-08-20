import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import BatchMetaCard from './BatchMetaCard.vue'
import { ElCollapse, ElCollapseItem, ElButton } from '../../tests/stubs'

const batch = {
  id: 'BATCH-42',
  schedule_time: '2026-08-21 09:00',
  started_at: '2026-08-21 09:01',
  finished_at: '2026-08-21 09:05',
  account_count: 10,
}

const mountIt = (over: Record<string, unknown> = {}) =>
  mount(BatchMetaCard, {
    props: { batch, accountCount: 8, metaOpen: ['meta'], ...over },
    global: { stubs: { ElCollapse, ElCollapseItem, ElButton } },
  })

describe('BatchMetaCard', () => {
  it('渲染批次 ID、时间与账号数', () => {
    const w = mountIt()
    const text = w.text()
    expect(text).toContain('BATCH-42')
    expect(text).toContain('2026-08-21 09:00')
    expect(text).toContain('2026-08-21 09:01')
    expect(text).toContain('2026-08-21 09:05')
    expect(text).toContain('批次记录 10')
    expect(text).toContain('实际展示 8')
  })

  it('未设置的时间显示占位', () => {
    const w = mountIt({ batch: { ...batch, schedule_time: undefined, started_at: undefined, finished_at: undefined } })
    expect(w.text()).toContain('未设置')
    expect(w.text()).toContain('—')
  })

  it('点击复制按钮调用 clipboard 并提示成功', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const w = mountIt()
    const btn = w.findAll('button').find(b => b.text().includes('复制'))!
    await btn.trigger('click')
    expect(writeText).toHaveBeenCalledWith('BATCH-42')
    vi.unstubAllGlobals()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })
})
