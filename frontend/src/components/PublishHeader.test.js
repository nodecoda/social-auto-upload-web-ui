import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PublishHeader from './PublishHeader.vue'

const stubs = { ElButton: { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['disabled'] } }

describe('PublishHeader', () => {
  it('渲染标题与四个操作按钮', () => {
    const w = mount(PublishHeader, { props: { hasAccounts: true }, global: { stubs } })
    expect(w.text()).toContain('发布视频')
    expect(w.text()).toContain('保存草稿')
    expect(w.text()).toContain('一键填写')
    expect(w.text()).toContain('批量设置')
    expect(w.text()).toContain('一键发布')
  })

  it('有 draftId 时按钮文案为「更新草稿」', () => {
    const w = mount(PublishHeader, { props: { draftId: 123, hasAccounts: true }, global: { stubs } })
    expect(w.text()).toContain('更新草稿')
  })

  it('自定义 title 生效', () => {
    const w = mount(PublishHeader, { props: { title: '图集发布', hasAccounts: true }, global: { stubs } })
    expect(w.text()).toContain('图集发布')
  })

  it('disableOneClick 时一键填写禁用', () => {
    const w = mount(PublishHeader, { props: { disableOneClick: true, hasAccounts: false }, global: { stubs } })
    const btns = w.findAll('button')
    const fill = btns.find(b => b.text().includes('一键填写'))
    expect(fill.attributes('disabled')).toBeDefined()
  })

  it('无账号时批量设置按钮禁用', () => {
    const w = mount(PublishHeader, { props: { hasAccounts: false }, global: { stubs } })
    const btns = w.findAll('button')
    const batch = btns.find(b => b.text().includes('批量设置'))
    expect(batch.attributes('disabled')).toBeDefined()
  })

  it('发布中显示「发布中...」并禁用发布按钮', () => {
    const w = mount(PublishHeader, { props: { publishing: true, hasAccounts: true }, global: { stubs } })
    expect(w.text()).toContain('发布中...')
    const btns = w.findAll('button')
    const publish = btns.find(b => b.text().includes('发布中'))
    expect(publish.attributes('disabled')).toBeDefined()
  })

  it('有平台名时显示个性化标签', () => {
    const w = mount(PublishHeader, { props: { platformName: '抖音', platformBgColor: '#f00', platformColor: '#fff' }, global: { stubs } })
    expect(w.text()).toContain('抖音 · 个性化设置')
    const tag = w.find('.platform-tag')
    expect(tag.attributes('style')).toContain('rgb(255, 0, 0)')
  })

  it('点击按钮依次发出对应事件', async () => {
    const w = mount(PublishHeader, { props: { hasAccounts: true }, global: { stubs } })
    const btns = w.findAll('button')
    const btnOf = t => btns.find(b => b.text().includes(t))
    await btnOf('保存草稿').trigger('click')
    expect(w.emitted('save-draft')).toBeTruthy()
    await btnOf('一键填写').trigger('click')
    expect(w.emitted('one-click')).toBeTruthy()
    await btnOf('批量设置').trigger('click')
    expect(w.emitted('batch-set')).toBeTruthy()
    await btnOf('一键发布').trigger('click')
    expect(w.emitted('publish')).toBeTruthy()
  })
})
