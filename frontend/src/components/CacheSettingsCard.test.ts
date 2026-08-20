import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CacheSettingsCard, { type CacheInfoState } from './CacheSettingsCard.vue'
import { type ExtractPropTypes } from 'vue'

const fullInfo: CacheInfoState = {
  frames: { count: 12, size: 1024 * 1024 * 3.5 },
  logs: { count: 100, size: 2048, oldCount: 8 },
  s3_videos: { count: 3, size: 500 },
  covers: { count: 2, size: 4096 },
}

const emptyInfo: CacheInfoState = {
  frames: { count: 0, size: 0 },
  logs: { count: 0, size: 0, oldCount: 0 },
  s3_videos: { count: 0, size: 0 },
  covers: { count: 0, size: 0 },
}

const mountIt = (over: Partial<ExtractPropTypes<typeof CacheSettingsCard['props']>> = {}) =>
  mount(CacheSettingsCard, {
    props: { cacheInfo: fullInfo, clearing: false, ...over },
  })

describe('CacheSettingsCard', () => {
  it('renders title and four cache targets', () => {
    const w = mountIt()
    expect(w.text()).toContain('缓存管理')
    expect(w.text()).toContain('清理抽帧缓存')
    expect(w.text()).toContain('清理日志文件')
    expect(w.text()).toContain('S3 视频缓存')
    expect(w.text()).toContain('清理封面缓存')
    expect(w.findAll('.setting-row')).toHaveLength(4)
  })

  it('formats cache sizes with MB/KB units', () => {
    const w = mountIt()
    expect(w.text()).toContain('12 个文件 · 3.5MB')
    expect(w.text()).toContain('8 个过期文件 · 2.0KB')
  })

  it('shows empty state when no cache', () => {
    const w = mountIt({ cacheInfo: emptyInfo })
    expect(w.text()).toContain('无缓存')
    expect(w.text()).toContain('无过期日志')
  })

  it('emits clear with target on button click', async () => {
    const w = mountIt()
    const btns = w.findAll('button.cache-btn')
    expect(btns).toHaveLength(4)
    for (const target of ['frames', 'logs', 's3_videos', 'covers']) {
      const idx = ['frames', 'logs', 's3_videos', 'covers'].indexOf(target)
      await btns[idx].trigger('click')
      const emitted = w.emitted('clear')!
      expect(emitted[emitted.length - 1]).toEqual([target])
    }
  })

  it('disables buttons when clearing is in progress', () => {
    const w = mountIt({ clearing: true })
    const btns = w.findAll('button.cache-btn')
    btns.forEach(b => expect(b.attributes('disabled')).toBeDefined())
    expect(w.text()).toContain('清理中...')
  })

  it('disables button when target has no cache', () => {
    const w = mountIt({ cacheInfo: emptyInfo })
    const btns = w.findAll('button.cache-btn')
    btns.forEach(b => expect(b.attributes('disabled')).toBeDefined())
  })
})
