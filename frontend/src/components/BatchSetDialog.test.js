import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import {
  ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElTag, ElDatePicker, ElMessage,
} from '../../tests/stubs.js'
import BatchSetDialog from './BatchSetDialog.vue'

vi.mock('element-plus', () => ({ ElMessage }))

const platforms = [
  { key: 'douyin', name: '抖音', count: 2, logo: '' },
  { key: 'xiaohongshu', name: '小红书', count: 1, logo: '' },
  { key: 'weibo', name: '微博', count: 0, logo: '' },
]

const mountIt = (over = {}) => mount(BatchSetDialog, {
  props: { modelValue: false, platforms, ...over },
  global: { stubs: { ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElTag, ElDatePicker } },
})

/** 打开对话框(触发 watch 重置/预选) */
const open = async (w) => { await w.setProps({ modelValue: true }); await w.vm.$nextTick() }

const cardOf = (w, name) => w.findAll('.channel-card').find(c => c.text().includes(name))

describe('BatchSetDialog', () => {
  beforeEach(() => {
    ElMessage.warning.mockClear()
  })

  it('关闭时不渲染对话框内容,打开后渲染标题与全部字段标签', async () => {
    const w = mountIt()
    expect(w.find('.el-dialog-stub').exists()).toBe(false)
    await open(w)
    expect(w.find('.el-dialog-stub').exists()).toBe(true)
    const text = w.text()
    for (const label of ['批量设置', '标题', '描述', '标签', '定时发布', '渠道']) {
      expect(text).toContain(label)
    }
    expect(w.find('input[placeholder="留空表示清空原值"]').exists()).toBe(true)
    expect(w.find('.el-date-picker-stub').exists()).toBe(true)
  })

  it('打开时预选全部 count>0 渠道,count=0 渠道禁用且未选中', async () => {
    const w = mountIt()
    await open(w)
    const douyin = cardOf(w, '抖音')
    const xhs = cardOf(w, '小红书')
    const weibo = cardOf(w, '微博')
    expect(douyin.attributes('aria-checked')).toBe('true')
    expect(xhs.attributes('aria-checked')).toBe('true')
    expect(weibo.attributes('aria-checked')).toBe('false')
    expect(weibo.attributes('aria-disabled')).toBe('true')
    expect(douyin.attributes('aria-disabled')).toBe('false')
    expect(douyin.classes()).toContain('is-checked')
  })

  it('无 logo 渠道渲染首字母回退标识', async () => {
    const w = mountIt()
    await open(w)
    expect(cardOf(w, '抖音').find('.channel-logo-fallback').text()).toBe('抖')
    expect(cardOf(w, '抖音').find('.channel-count').text()).toBe('2')
  })

  it('点击渠道卡片切换选中态;禁用渠道点击无效', async () => {
    const w = mountIt()
    await open(w)
    const douyin = cardOf(w, '抖音')
    await douyin.trigger('click')
    expect(douyin.attributes('aria-checked')).toBe('false')
    await douyin.trigger('click')
    expect(douyin.attributes('aria-checked')).toBe('true')
    const weibo = cardOf(w, '微博')
    await weibo.trigger('click')
    expect(weibo.attributes('aria-checked')).toBe('false')
  })

  it('无任何有效渠道时应用按钮禁用', async () => {
    const w = mountIt({ platforms: [{ key: 'weibo', name: '微博', count: 0, logo: '' }] })
    await open(w)
    const btns = w.findAll('button')
    const partial = btns.find(b => b.text().includes('仅应用已填写'))
    const full = btns.find(b => b.text().includes('全量应用'))
    expect(partial.attributes('disabled')).toBeDefined()
    expect(full.attributes('disabled')).toBeDefined()
  })

  it('回车添加标签,重复/空标签不重复添加,关闭标签可移除', async () => {
    const w = mountIt()
    await open(w)
    const input = w.find('input[placeholder="输入标签内容，按回车添加"]')
    await input.setValue('数码')
    await input.trigger('keyup', { key: 'Enter' })
    await input.setValue('数码') // 重复
    await input.trigger('keyup', { key: 'Enter' })
    await input.setValue('   ') // 空白
    await input.trigger('keyup', { key: 'Enter' })
    const tags = w.findAll('.el-tag-stub')
    expect(tags).toHaveLength(1)
    expect(tags[0].text()).toBe('#数码')
    // 关闭第一个标签
    await tags[0].trigger('click')
    expect(w.findAll('.el-tag-stub')).toHaveLength(0)
  })

  it('超过 10 个标签触发 ElMessage.warning 且不继续添加', async () => {
    const w = mountIt()
    await open(w)
    const input = w.find('input[placeholder="输入标签内容，按回车添加"]')
    for (let i = 1; i <= 10; i++) {
      await input.setValue(`tag${i}`)
      await input.trigger('keyup', { key: 'Enter' })
    }
    expect(w.findAll('.el-tag-stub')).toHaveLength(10)
    await input.setValue('tag11')
    await input.trigger('keyup', { key: 'Enter' })
    expect(ElMessage.warning).toHaveBeenCalledTimes(1)
    expect(ElMessage.warning).toHaveBeenCalledWith('最多 10 个标签')
    expect(w.findAll('.el-tag-stub')).toHaveLength(10)
  })

  it('取消按钮发出 update:modelValue false', async () => {
    const w = mountIt()
    await open(w)
    const cancel = w.findAll('button').find(b => b.text().includes('取消'))
    await cancel.trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([[false]])
  })

  it('「仅应用已填写」发出 apply:已选渠道 + 已填字段 + partial 模式,并关闭', async () => {
    const w = mountIt()
    await open(w)
    // 去掉小红书,保留抖音
    await cardOf(w, '小红书').trigger('click')
    await w.find('input[placeholder="留空表示清空原值"]').setValue('我的标题')
    await w.find('input[placeholder="输入标签内容，按回车添加"]').setValue('美食')
    await w.find('input[placeholder="输入标签内容，按回车添加"]').trigger('keyup', { key: 'Enter' })
    await w.find('.el-date-picker-stub').setValue('2026-08-20 10:00:00')

    const partial = w.findAll('button').find(b => b.text().includes('仅应用已填写'))
    await partial.trigger('click')

    const [keys, payload] = w.emitted('apply')[0]
    expect(keys).toEqual(['douyin'])
    expect(payload).toEqual({
      title: '我的标题',
      description: '',
      tags: ['美食'],
      scheduleTime: '2026-08-20 10:00:00',
      mode: 'partial',
    })
    expect(w.emitted('update:modelValue')).toEqual([[false]])
  })

  it('「全量应用」发出 apply 载荷 mode=full', async () => {
    const w = mountIt()
    await open(w)
    const full = w.findAll('button').find(b => b.text().includes('全量应用'))
    await full.trigger('click')
    const [keys, payload] = w.emitted('apply')[0]
    expect(keys).toEqual(['douyin', 'xiaohongshu'])
    expect(payload).toMatchObject({ title: '', description: '', tags: [], scheduleTime: '', mode: 'full' })
  })

  it('自定义 title prop 生效', async () => {
    const w = mountIt({ title: '批量修改' })
    await open(w)
    expect(w.find('.el-dialog-stub-title').text()).toBe('批量修改')
  })
})
