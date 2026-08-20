import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MaterialCard from './MaterialCard.vue'

const imageMat = {
  id: 1,
  original_filename: 'photo.jpg',
  file_type: 'image',
  stored_path: '/data/photo.jpg',
  storage_type: 's3',
  file_size: 2048,
  upload_time: '2026-08-01 10:00:00',
}

const videoMat = {
  id: 2,
  original_filename: 'clip.mp4',
  file_type: 'video',
  stored_path: '/data/clip.mp4',
  thumbnail_url: '/data/clip.jpg',
  duration: 30,
}

describe('MaterialCard', () => {
  it('renders image material with name, size and storage badge', () => {
    const wrapper = mount(MaterialCard, { props: { mat: imageMat } })
    expect(wrapper.text()).toContain('photo.jpg')
    expect(wrapper.text()).toContain('2.0 KB')
    expect(wrapper.text()).toContain('S3')
    expect(wrapper.find('img').exists()).toBe(true)
  })

  it('emits select when card is clicked', async () => {
    const wrapper = mount(MaterialCard, { props: { mat: imageMat } })
    await wrapper.trigger('click')
    expect(wrapper.emitted('select')).toHaveLength(1)
  })

  it('shows check mark when selected', () => {
    const wrapper = mount(MaterialCard, { props: { mat: imageMat, selected: true } })
    expect(wrapper.find('.msd-card-check').exists()).toBe(true)
  })

  it('renders video thumb with play button and duration', () => {
    const wrapper = mount(MaterialCard, { props: { mat: videoMat } })
    expect(wrapper.find('.msd-card-play-btn').exists()).toBe(true)
    expect(wrapper.find('.msd-card-video-badge').exists()).toBe(true)
    expect(wrapper.text()).toContain('30s')
  })

  it('emits toggle-play when play button clicked (and not when card clicked)', async () => {
    const wrapper = mount(MaterialCard, { props: { mat: videoMat } })
    await wrapper.find('.msd-card-play-btn').trigger('click')
    expect(wrapper.emitted('toggle-play')).toHaveLength(1)
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('renders video element when playing and emits video-ended', async () => {
    const wrapper = mount(MaterialCard, { props: { mat: videoMat, playing: true } })
    expect(wrapper.find('video').exists()).toBe(true)
    await wrapper.find('video').trigger('ended')
    expect(wrapper.emitted('video-ended')).toHaveLength(1)
  })
})
