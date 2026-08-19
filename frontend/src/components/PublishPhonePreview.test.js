import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PublishPhonePreview from './PublishPhonePreview.vue'

describe('PublishPhonePreview', () => {
  it('无视频时显示空态上传区', () => {
    const w = mount(PublishPhonePreview)
    expect(w.find('.phone-empty').exists()).toBe(true)
    expect(w.text()).toContain('上传视频')
    expect(w.find('video').exists()).toBe(false)
  })

  it('有视频时渲染 video 并显示文件名', () => {
    const w = mount(PublishPhonePreview, { props: { videoData: { url: '/v.mp4', name: 'demo.mp4' } } })
    const video = w.find('video')
    expect(video.exists()).toBe(true)
    expect(video.attributes('src')).toBe('/v.mp4')
    expect(w.find('.phone-empty').exists()).toBe(false)
    expect(w.find('.phone-info-name').text()).toBe('demo.mp4')
  })

  it('modeTab 横版时 mockup 加 landscape class', () => {
    const w = mount(PublishPhonePreview, { props: { modeTab: 'landscape' } })
    expect(w.find('.phone-mockup').classes()).toContain('landscape')
  })

  it('点击空态/本地上传发出 upload 事件', async () => {
    const w = mount(PublishPhonePreview)
    await w.find('.phone-empty').trigger('click')
    expect(w.emitted('upload')).toBeTruthy()
    const btns = w.findAll('button')
    await btns.find(b => b.text().includes('本地上传')).trigger('click')
    expect(w.emitted('upload').length).toBe(2)
  })

  it('点击素材库发出 library 事件', async () => {
    const w = mount(PublishPhonePreview)
    const btns = w.findAll('button')
    await btns.find(b => b.text().includes('素材库')).trigger('click')
    expect(w.emitted('library')).toBeTruthy()
  })

  it('有视频时点击删除按钮发出 remove 事件', async () => {
    const w = mount(PublishPhonePreview, { props: { videoData: { url: '/v.mp4', name: 'demo.mp4' } } })
    await w.find('.phone-info-remove').trigger('click')
    expect(w.emitted('remove')).toBeTruthy()
  })
})
