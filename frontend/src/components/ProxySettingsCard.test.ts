import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ProxySettingsCard from './ProxySettingsCard.vue'
import { ElInput } from '../../tests/stubs'

const overseasPlatforms = [
  { key: 'youtube', name: 'YouTube', logo: '/yt.png' },
  { key: 'tiktok', name: 'TikTok', logo: '/tt.png' },
]

const mountIt = (over: Record<string, unknown> = {}) =>
  mount(ProxySettingsCard, {
    props: { proxyUrl: '', overseasPlatforms, ...over },
    global: { stubs: { ElInput } },
  })

describe('ProxySettingsCard', () => {
  it('渲染标题、代理输入框与海外平台标签', () => {
    const w = mountIt()
    expect(w.text()).toContain('网络代理')
    expect(w.find('.el-input-stub').attributes('placeholder')).toContain('7897')
    const tags = w.findAll('.proxy-tag')
    expect(tags.map(t => t.text().trim())).toEqual(['YouTube', 'TikTok'])
  })

  it('代理地址回显', () => {
    const w = mountIt({ proxyUrl: 'http://127.0.0.1:7897' })
    expect((w.find('.el-input-stub').element as HTMLInputElement).value).toBe('http://127.0.0.1:7897')
  })

  it('输入代理地址 emit update:proxyUrl', async () => {
    const w = mountIt()
    await w.find('.el-input-stub').setValue('http://proxy:8080')
    expect(w.emitted('update:proxyUrl')).toEqual([['http://proxy:8080']])
  })
})
