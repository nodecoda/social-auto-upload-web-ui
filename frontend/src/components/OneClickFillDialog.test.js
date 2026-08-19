import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElDialog, ElEmpty, ElIcon, ElPagination } from '../../tests/stubs.js'
import OneClickFillDialog from './OneClickFillDialog.vue'

// 命名导出 http(见组件 L49 `import { http } from '@/utils/request'`)
vi.mock('@/utils/request', () => ({ http: vi.fn() }))
import { http } from '@/utils/request'

const MIN_5 = 5 * 60 * 1000
const HOUR_2 = 2 * 60 * 60 * 1000

const videoRecord = {
  id: 1, type: 'video', title: '视频标题', description: '这是一段描述',
  channels: [{ platform: '抖音', account_id: 10 }],
  created_at: new Date(Date.now() - MIN_5).toISOString(),
  thumbnail_path: 'videos/a.mp4',
}
const imageRecord = {
  id: 2, type: 'image', title: '图集标题', description: '',
  channels: [{ account_id: 3 }],
  created_at: new Date(Date.now() - HOUR_2).toISOString(),
  first_image_id: 5,
}

const mountIt = (over = {}) => mount(OneClickFillDialog, {
  props: { modelValue: false, type: 'video', ...over },
  global: {
    stubs: { ElDialog, ElEmpty, ElIcon, ElPagination },
    directives: { loading: {} },
  },
})

const open = async (w) => { await w.setProps({ modelValue: true }); await flushPromises() }

describe('OneClickFillDialog', () => {
  beforeEach(() => {
    http.get = vi.fn()
  })

  it('打开时按 type 请求历史模板,无记录时渲染空态(视频)', async () => {
    http.get.mockResolvedValue({ data: { list: [], total: 0 } })
    const w = mountIt()
    expect(http.get).not.toHaveBeenCalled()
    await open(w)
    expect(http.get).toHaveBeenCalledWith('/api/v2/publish-templates', { type: 'video', page: 1, page_size: 20 })
    expect(w.find('.el-empty-stub').text()).toContain('还没有可用的历史记录，去 视频发布 试试？')
    expect(w.findAll('.card')).toHaveLength(0)
    expect(w.find('.el-pagination-stub').exists()).toBe(false)
  })

  it('type=image 时空态文案指向图集发布', async () => {
    http.get.mockResolvedValue({ data: { list: [], total: 0 } })
    const w = mountIt({ type: 'image' })
    await open(w)
    expect(http.get).toHaveBeenCalledWith('/api/v2/publish-templates', { type: 'image', page: 1, page_size: 20 })
    expect(w.find('.el-empty-stub').text()).toContain('去 图集发布 试试？')
  })

  it('渲染记录卡片:标题、描述截断、渠道标签、相对时间与视频封面', async () => {
    http.get.mockResolvedValue({ data: { list: [videoRecord], total: 1 } })
    const w = mountIt()
    await open(w)
    const card = w.find('.card')
    expect(card.find('.card-title').text()).toBe('视频标题')
    expect(card.find('.card-desc').text()).toBe('这是一段描述')
    expect(card.find('.channel-tag').text()).toBe('抖音')
    expect(card.find('.card-time').text()).toBe('5 分钟前')
    // 视频缩略图走封面代理 URL
    expect(card.find('.card-cover img').attributes('src')).toBe('http://localhost:5409/api/materials/file/videos/a.mp4')
  })

  it('image 记录:请求素材详情生成封面,无 platform 渠道显示「未知平台」', async () => {
    http.get.mockResolvedValueOnce({ data: { list: [imageRecord], total: 1 } })
      .mockResolvedValueOnce({ data: { stored_path: 'mats/5.jpg' } })
    const w = mountIt({ type: 'image' })
    await open(w)
    const card = w.find('.card')
    expect(http.get).toHaveBeenCalledWith('/api/materials/5')
    expect(card.find('.card-cover img').attributes('src')).toBe('http://localhost:5409/api/materials/file/mats/5.jpg')
    expect(card.find('.channel-tag').text()).toBe('未知平台')
    expect(card.find('.card-time').text()).toBe('2 小时前')
  })

  it('封面请求失败时降级为空封面,不阻塞列表渲染', async () => {
    http.get.mockResolvedValueOnce({ data: { list: [imageRecord], total: 1 } })
      .mockRejectedValueOnce(new Error('404'))
    const w = mountIt({ type: 'image' })
    await open(w)
    expect(w.find('.cover-placeholder').exists()).toBe(true)
    expect(w.find('.card-title').text()).toBe('图集标题')
  })

  it('点击卡片发出 pick(完整记录)并关闭对话框', async () => {
    http.get.mockResolvedValue({ data: { list: [videoRecord], total: 1 } })
    const w = mountIt()
    await open(w)
    await w.find('.card').trigger('click')
    expect(w.emitted('pick')).toEqual([[videoRecord]])
    expect(w.emitted('update:modelValue')).toEqual([[false]])
  })

  it('total>0 时渲染分页,翻页触发重新加载(page=2)', async () => {
    http.get.mockResolvedValue({ data: { list: [videoRecord], total: 25 } })
    const w = mountIt()
    await open(w)
    const pag = w.find('.el-pagination-stub')
    expect(pag.exists()).toBe(true)
    expect(pag.text()).toContain('共 25 条')
    await w.find('.pagination-next').trigger('click')
    expect(http.get).toHaveBeenLastCalledWith('/api/v2/publish-templates', { type: 'video', page: 2, page_size: 20 })
  })



  it('相对时间格式化:覆盖天前与超一周的日期文案', async () => {
    const day3 = { id: 5, type: 'video', title: '三天前', description: '', channels: [], created_at: new Date(Date.now() - 3 * 86400 * 1000).toISOString() }
    const day30 = { id: 6, type: 'video', title: '一个月前', description: '', channels: [], created_at: new Date(Date.now() - 30 * 86400 * 1000).toISOString() }
    http.get.mockResolvedValue({ data: { list: [day3, day30], total: 2 } })
    const w = mountIt()
    await open(w)
    const times = w.findAll('.card-time').map(t => t.text())
    expect(times[0]).toBe('3 天前')
    expect(times[1]).toBe(new Date(day30.created_at).toLocaleDateString('zh-CN'))
  })

  it('视频无缩略图 / 素材请求返回空时降级为占位封面', async () => {
    const noThumb = { id: 3, type: 'video', title: '无缩略图', description: '', channels: [], created_at: new Date().toISOString() }
    const badImg = { id: 4, type: 'image', title: '坏素材', description: '', channels: [], created_at: new Date().toISOString(), first_image_id: 7 }
    http.get
      .mockResolvedValueOnce({ data: { list: [noThumb, badImg], total: 2 } })
      .mockResolvedValueOnce({ data: null })
    const w = mountIt()
    await open(w)
    expect(http.get).toHaveBeenCalledWith('/api/materials/7')
    expect(w.findAll('.cover-placeholder')).toHaveLength(2)
    expect(w.findAll('.card-cover img')).toHaveLength(0)
  })

  it('请求失败时渲染空态且不抛错', async () => {
    http.get.mockRejectedValue(new Error('network'))
    const w = mountIt()
    await open(w)
    expect(w.find('.el-empty-stub').exists()).toBe(true)
    expect(w.findAll('.card')).toHaveLength(0)
    expect(w.find('.el-pagination-stub').exists()).toBe(false)
  })
})
