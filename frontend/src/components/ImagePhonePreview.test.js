import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ImagePhonePreview from './ImagePhonePreview.vue'

const images = [
  { name: 'a.jpg', url: '/a.jpg' },
  { name: 'b.jpg', url: '/b.jpg' },
]

const stubs = {
  ImageCarousel: { template: '<div class="carousel-stub" @click="$emit(\'change\', 2)" />' },
  ElIcon: { template: '<i><slot /></i>' },
}

const mountIt = (over = {}) => mount(ImagePhonePreview, {
  props: { images: [], previewIndex: 0, ...over },
  global: { stubs },
})

describe('ImagePhonePreview', () => {
  it('无图时显示空态上传区', () => {
    const w = mountIt()
    expect(w.find('.phone-empty').exists()).toBe(true)
    expect(w.text()).toContain('上传图片')
    expect(w.find('.carousel-stub').exists()).toBe(false)
    expect(w.find('.phone-panel-info').exists()).toBe(false)
  })

  it('有图时渲染轮播与信息栏', () => {
    const w = mountIt({ images })
    expect(w.find('.carousel-stub').exists()).toBe(true)
    expect(w.find('.phone-empty').exists()).toBe(false)
    const info = w.find('.phone-panel-info')
    expect(info.exists()).toBe(true)
    expect(info.text()).toContain('a.jpg')
    expect(info.text()).toContain('1/2')
  })

  it('previewIndex 指向当前图片并显示计数', () => {
    const w = mountIt({ images, previewIndex: 1 })
    expect(w.find('.phone-info-name').text()).toBe('b.jpg')
    expect(w.find('.phone-info-count').text()).toBe('2/2')
  })

  it('点击空态/本地上传发出 upload', async () => {
    const w = mountIt()
    await w.find('.phone-empty').trigger('click')
    expect(w.emitted('upload')).toBeTruthy()
  })

  it('放大预览按钮在有图时出现并发出 preview', async () => {
    const w = mountIt({ images })
    const btn = w.findAll('button').find(b => b.text().includes('放大预览'))
    expect(btn).toBeTruthy()
    await btn.trigger('click')
    expect(w.emitted('preview')).toBeTruthy()
  })

  it('轮播 change 事件透传为 carousel-change', async () => {
    const w = mountIt({ images })
    await w.find('.carousel-stub').trigger('click')
    expect(w.emitted('carousel-change')).toEqual([[2]])
  })

  it('素材库按钮发出 library', async () => {
    const w = mountIt({ images })
    const btn = w.findAll('button').find(b => b.text().includes('素材库'))
    await btn.trigger('click')
    expect(w.emitted('library')).toBeTruthy()
  })
})
