import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PublishSettingsCard from './PublishSettingsCard.vue'
import { ElInputNumber, ElSelect, ElOption, ElSwitch } from '../../tests/stubs'

const base = {
  autoFillTitle: true,
  autoSaveDraft: true,
  autoSaveInterval: 10,
  accountCheckMode: 'pre-publish',
}

const mountIt = (over: Record<string, unknown> = {}) =>
  mount(PublishSettingsCard, {
    props: { ...base, ...over },
    global: { stubs: { ElSwitch, ElInputNumber, ElSelect, ElOption } },
  })

describe('PublishSettingsCard', () => {
  it('渲染全部设置行与选项', () => {
    const w = mountIt()
    expect(w.text()).toContain('上传视频后自动填充标题')
    expect(w.text()).toContain('自动保存草稿')
    expect(w.text()).toContain('自动保存间隔（秒）')
    expect(w.text()).toContain('账号登录状态检查机制')
    expect(w.find('.el-option-stub').text()).toBe('发布前检测（默认）')
  })

  it('autoSaveDraft 关闭时隐藏间隔行', () => {
    const w = mountIt({ autoSaveDraft: false })
    expect(w.text()).not.toContain('自动保存间隔')
  })

  it('切换开关 emit update:autoFillTitle / update:autoSaveDraft', async () => {
    const w = mountIt()
    const switches = w.findAll('.el-switch-stub')
    await switches[0].trigger('click') // autoFillTitle
    await switches[1].trigger('click') // autoSaveDraft
    expect(w.emitted('update:autoFillTitle')).toEqual([[false]])
    expect(w.emitted('update:autoSaveDraft')).toEqual([[false]])
  })

  it('修改间隔 emit update:autoSaveInterval', async () => {
    const w = mountIt()
    await w.find('.el-input-number-stub').setValue(30)
    expect(w.emitted('update:autoSaveInterval')).toEqual([[30]])
  })
})
