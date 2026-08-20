import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SponsorQrCard from './SponsorQrCard.vue'

const qr = {
  name: '支付宝',
  img: '/alipay.jpg',
  accent: '#1677FF',
  iconBg: 'linear-gradient(135deg, #1677FF, #00A6FF)',
  icon: { render: () => null },
  emoji: '💙',
  slogan: '推荐 · 实时到账',
}

const mountIt = () => mount(SponsorQrCard, { props: { qr } })

describe('SponsorQrCard', () => {
  it('渲染二维码名称、标签、图片与标语', () => {
    const w = mountIt()
    expect(w.find('.qr-name').text()).toBe('支付宝')
    expect(w.find('.qr-tag').text()).toBe('扫码支持')
    expect(w.find('img').attributes('src')).toBe('/alipay.jpg')
    expect(w.find('.qr-card-foot').text()).toContain('推荐 · 实时到账')
  })

  it('通过 --accent 变量应用品牌色', () => {
    const w = mountIt()
    expect(w.find('.qr-card').attributes('style')).toContain('--accent: #1677FF')
  })

  it('点击图片区域 emit preview', async () => {
    const w = mountIt()
    await w.find('.qr-img-wrap').trigger('click')
    expect(w.emitted('preview')).toEqual([[qr]])
  })
})
