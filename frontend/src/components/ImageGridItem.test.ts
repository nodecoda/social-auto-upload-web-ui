import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ImageGridItem from './ImageGridItem.vue'
import { type ExtractPropTypes } from 'vue'

const ElProgress = {
  props: ['percentage', 'width', 'strokeWidth'],
  template: '<div class="el-progress-stub" :data-percentage="percentage"></div>',
}

const ElIcon = { template: '<i class="el-icon-stub"><slot /></i>' }

const baseImage = {
  id: 1,
  name: 'photo.jpg',
  url: 'https://example.com/photo.jpg',
  uploading: false,
  progress: 100,
}

const mountIt = (over: Partial<ExtractPropTypes<typeof ImageGridItem['props']>> = {}) =>
  mount(ImageGridItem, {
    props: { image: { ...baseImage, ...over.image }, index: over.index ?? 0 },
    global: { stubs: { ElProgress, ElIcon } },
  })

describe('ImageGridItem', () => {
  it('renders image, name and index badge', () => {
    const w = mountIt({ index: 2 })
    const img = w.find('img')
    expect(img.attributes('src')).toBe(baseImage.url)
    expect(img.attributes('alt')).toBe(baseImage.name)
    expect(w.text()).toContain('photo.jpg')
    expect(w.find('.index-badge').text()).toBe('3')
    expect(w.find('.sort-handle').exists()).toBe(true)
  })

  it('shows uploading progress overlay when uploading', () => {
    const w = mountIt({ image: { uploading: true, progress: 42 } })
    expect(w.find('.uploading-overlay').exists()).toBe(true)
    expect(w.find('.el-progress-stub').attributes('data-percentage')).toBe('42')
    expect(w.find('.image-overlay').exists()).toBe(false)
  })

  it('shows hover overlay actions when not uploading', () => {
    const w = mountIt()
    expect(w.find('.uploading-overlay').exists()).toBe(false)
    expect(w.findAll('.overlay-btn')).toHaveLength(3)
  })

  it('emits re-upload with index on retry button click', async () => {
    const w = mountIt({ index: 1 })
    await w.findAll('.overlay-btn')[0].trigger('click')
    expect(w.emitted('re-upload')).toEqual([[1]])
  })

  it('emits open-material-library with index on library button click', async () => {
    const w = mountIt({ index: 1 })
    await w.findAll('.overlay-btn')[1].trigger('click')
    expect(w.emitted('open-material-library')).toEqual([[1]])
  })

  it('emits remove with index on delete button click', async () => {
    const w = mountIt({ index: 1 })
    await w.findAll('.overlay-btn')[2].trigger('click')
    expect(w.emitted('remove')).toEqual([[1]])
  })

  it('replaces broken image src with placeholder on error', async () => {
    const w = mountIt()
    const img = w.find('img')
    await img.trigger('error')
    expect(img.attributes('src')).toContain('data:image/svg+xml;base64')
  })
})
