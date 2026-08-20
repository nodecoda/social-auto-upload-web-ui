import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ImportAccountDialog from './ImportAccountDialog.vue'
import { ElButton, ElDialog, ElIcon, ElInput } from '../../tests/stubs'
import { accountApi } from '@/api/account'

const { ElMessage, getImportSupportedPlatformsMock, startImportAccountMock } = vi.hoisted(() => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn(), info: vi.fn() },
  getImportSupportedPlatformsMock: vi.fn(),
  startImportAccountMock: vi.fn(),
}))
vi.mock('element-plus', () => ({ ElMessage }))
vi.mock('@/api/account', () => ({
  accountApi: { getImportSupportedPlatforms: getImportSupportedPlatformsMock, startImportAccount: startImportAccountMock },
}))

/** EventSource 假实现:捕获实例,测试里手动触发 onmessage/onerror */
class FakeEventSource {
  static instances: FakeEventSource[] = []
  onmessage: ((ev: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }
}

const platforms = [
  { id: 1, key: 'douyin', name: '抖音', letter: 'D' },
  { id: 2, key: 'xiaohongshu', name: '小红书', letter: 'X' },
]

const mountIt = () =>
  mount(ImportAccountDialog, {
    props: { modelValue: false },
    global: { stubs: { ElButton, ElDialog, ElIcon, ElInput } },
  })

const open = async (w: VueWrapper) => { await w.setProps({ modelValue: true }); await flushPromises() }
const startBtn = (w: VueWrapper) => w.findAll('.el-button-stub').find(b => b.text().includes('开始导入'))!
const push = (es: FakeEventSource, payload: Record<string, unknown>) =>
  es.onmessage!({ data: JSON.stringify(payload) })

describe('ImportAccountDialog', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    getImportSupportedPlatformsMock.mockReset()
    startImportAccountMock.mockReset()
    ElMessage.error.mockClear()
    ElMessage.success.mockClear()
    ElMessage.warning.mockClear()
    getImportSupportedPlatformsMock.mockResolvedValue({ code: 200, data: platforms })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('打开时拉取支持导入的平台列表并渲染平台卡片', async () => {
    const w = mountIt()
    await open(w)
    expect(getImportSupportedPlatformsMock).toHaveBeenCalledTimes(1)
    expect(w.findAll('.platform-card-flat')).toHaveLength(2)
    expect(w.text()).toContain('抖音')
    expect(w.text()).toContain('小红书')
  })

  it('平台搜索过滤列表,无匹配时显示空态', async () => {
    const w = mountIt()
    await open(w)
    await w.find('.platform-search').setValue('小')
    expect(w.findAll('.platform-card-flat')).toHaveLength(1)
    expect(w.find('.card-name').text()).toBe('小红书')
    await w.find('.platform-search').setValue('不存在的平台')
    expect(w.findAll('.platform-card-flat')).toHaveLength(0)
    expect(w.find('.empty-platform').text()).toContain('未匹配到平台')
  })

  it('未选平台或 cookie 为空时开始导入按钮禁用', async () => {
    const w = mountIt()
    await open(w)
    expect(startBtn(w).attributes('disabled')).toBeDefined()
    await w.findAll('.platform-card-flat')[0].trigger('click')
    expect(startBtn(w).attributes('disabled')).toBeDefined()
    await w.find('.import-textarea').setValue('k1=v1; k2=v2')
    expect(startBtn(w).attributes('disabled')).toBeUndefined()
  })

  it('导入成功:SSE 进度推进→完成卡片→emit success', async () => {
    startImportAccountMock.mockResolvedValue({ code: 200, data: { task_id: 't1' } })
    const w = mountIt()
    await open(w)
    await w.findAll('.platform-card-flat')[0].trigger('click')
    await w.find('.import-textarea').setValue('k1=v1')
    await startBtn(w).trigger('click')
    await flushPromises()

    expect(startImportAccountMock).toHaveBeenCalledWith({ type: 1, cookie_str: 'k1=v1' })
    const es = FakeEventSource.instances.at(-1)!
    expect(es.url).toContain('/importAccount/stream?task_id=t1')
    expect(w.text()).toContain('解析 cookie 字符串')

    push(es, { step: 1, status: 'running', msg: '解析中' })
    await flushPromises()
    expect(w.text()).toContain('解析中')
    expect(w.text()).toContain('0/4') // importActiveStep 0 基,步骤 1 对应 0/4

    push(es, { step: 4, status: 'done', account_id: 42, userName: '张三', avatar: '' })
    await flushPromises()
    expect(es.close).toHaveBeenCalled()
    expect(w.find('.result-card').exists()).toBe(true)
    expect(w.find('.result-name').text()).toBe('张三')
    expect(w.find('.result-meta').text()).toContain('账号 #42')
    expect(w.text()).toContain('4/4')
    expect(ElMessage.success).toHaveBeenCalledWith('导入成功')
    expect(w.emitted('success')).toHaveLength(1)
  })

  it('SSE 报错:当前步骤标红,进度显示已中断,按钮变关闭', async () => {
    startImportAccountMock.mockResolvedValue({ code: 200, data: { task_id: 't2' } })
    const w = mountIt()
    await open(w)
    await w.findAll('.platform-card-flat')[0].trigger('click')
    await w.find('.import-textarea').setValue('k1=v1')
    await startBtn(w).trigger('click')
    await flushPromises()

    const es = FakeEventSource.instances.at(-1)!
    push(es, { step: 2, status: 'error', msg: 'cookie 无效' })
    await flushPromises()
    expect(w.findAll('.step-item')[1].classes()).toContain('is-error')
    expect(w.text()).toContain('已中断')
    expect(ElMessage.error).toHaveBeenCalledWith('导入失败: cookie 无效')
    const closeBtn = w.findAll('.el-button-stub').find(b => b.text().includes('关闭'))!
    expect(closeBtn.exists()).toBe(true)
  })

  it('启动任务失败:第一步标红并允许关闭', async () => {
    startImportAccountMock.mockResolvedValue({ code: 500, msg: '服务不可用', data: null })
    const w = mountIt()
    await open(w)
    await w.findAll('.platform-card-flat')[0].trigger('click')
    await w.find('.import-textarea').setValue('k1=v1')
    await startBtn(w).trigger('click')
    await flushPromises()
    expect(w.findAll('.step-item')[0].classes()).toContain('is-error')
    expect(w.text()).toContain('已中断')
    expect(w.find('.footer-btn-primary').text()).toContain('关闭')
  })

  it('取消按钮 emit update:modelValue(false)', async () => {
    const w = mountIt()
    await open(w)
    const cancel = w.findAll('.el-button-stub').find(b => b.text().includes('取消'))!
    await cancel.trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([[false]])
  })
})
