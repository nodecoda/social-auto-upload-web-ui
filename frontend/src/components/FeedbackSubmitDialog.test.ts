import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import FeedbackSubmitDialog from './FeedbackSubmitDialog.vue'
import { ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElUpload } from '../../tests/stubs'
import { submitFeedback } from '@/api/feedback'
import { http } from '@/utils/request'

const { ElMessage, submitFeedbackMock, httpPutMock } = vi.hoisted(() => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn(), info: vi.fn() },
  submitFeedbackMock: vi.fn(),
  httpPutMock: vi.fn(),
}))
vi.mock('element-plus', () => ({ ElMessage }))
vi.mock('@/api/feedback', () => ({ submitFeedback: submitFeedbackMock }))
vi.mock('@/utils/request', () => ({ http: { put: httpPutMock } }))

const mountIt = () =>
  mount(FeedbackSubmitDialog, {
    props: { modelValue: false },
    global: { stubs: { ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElUpload } },
  })

const open = async (w: VueWrapper) => { await w.setProps({ modelValue: true }); await w.vm.$nextTick() }
const submitBtn = (w: VueWrapper) => w.findAll('.el-button-stub').find(b => b.text().includes('提交'))!

describe('FeedbackSubmitDialog', () => {
  beforeEach(() => {
    localStorage.clear()
    submitFeedbackMock.mockReset()
    httpPutMock.mockReset()
    ElMessage.error.mockClear()
    ElMessage.success.mockClear()
    ElMessage.warning.mockClear()
    submitFeedbackMock.mockResolvedValue(undefined)
    httpPutMock.mockResolvedValue({})
  })

  it('关闭时不渲染,打开后预填 localStorage 邮箱并渲染表单字段', async () => {
    localStorage.setItem('global_user_email', 'pre@example.com')
    const w = mountIt()
    expect(w.find('.el-dialog-stub').exists()).toBe(false)
    await open(w)
    expect(w.find('.el-dialog-stub-title').text()).toBe('提交反馈')
    const inputs = w.findAll('.el-input-stub')
    expect(inputs[0].element as HTMLInputElement).toHaveProperty('value', 'pre@example.com')
    expect(inputs[0].attributes('placeholder')).toBe('your@email.com')
    expect(inputs[1].attributes('placeholder')).toBe('详细描述您遇到的问题或建议')
    expect(w.find('.el-upload-stub').exists()).toBe(true)
  })

  it('邮箱或内容为空时拦截并提示,不调用接口', async () => {
    const w = mountIt()
    await open(w)
    await submitBtn(w).trigger('click')
    expect(ElMessage.error).toHaveBeenCalledWith('邮箱和内容必填')
    expect(submitFeedbackMock).not.toHaveBeenCalled()
  })

  it('填写后提交成功:emit update:modelValue(false) + submit-success', async () => {
    const w = mountIt()
    await open(w)
    const inputs = w.findAll('.el-input-stub')
    await inputs[0].setValue('a@b.com')
    await inputs[1].setValue('希望支持批量导出')
    await submitBtn(w).trigger('click')
    await flushPromises()
    expect(submitFeedbackMock).toHaveBeenCalledTimes(1)
    expect(submitFeedbackMock.mock.calls[0][0]).toBeInstanceOf(FormData)
    expect(ElMessage.success).toHaveBeenCalledWith('提交成功')
    expect(w.emitted('update:modelValue')).toEqual([[false]])
    expect(w.emitted('submit-success')).toHaveLength(1)
  })

  it('修改邮箱后同步到 localStorage 与后端 settings', async () => {
    localStorage.setItem('global_user_email', 'old@b.com')
    const w = mountIt()
    await open(w)
    const inputs = w.findAll('.el-input-stub')
    await inputs[0].setValue('new@b.com')
    await inputs[1].setValue('内容')
    await submitBtn(w).trigger('click')
    await flushPromises()
    expect(localStorage.getItem('global_user_email')).toBe('new@b.com')
    expect(httpPutMock).toHaveBeenCalledWith('/api/v2/settings', { feedbackEmail: 'new@b.com' })
  })

  it('邮箱未变化时不重复写 localStorage 与后端', async () => {
    localStorage.setItem('global_user_email', 'same@b.com')
    const w = mountIt()
    await open(w)
    const inputs = w.findAll('.el-input-stub')
    await inputs[1].setValue('内容')
    await submitBtn(w).trigger('click')
    await flushPromises()
    expect(httpPutMock).not.toHaveBeenCalled()
  })

  it('超过 5MB 的文件被拒绝并提示', async () => {
    const w = mountIt()
    await open(w)
    const upload = w.findComponent({ name: 'ElUpload' })
    const onChange = upload.props('onChange') as (f: { size?: number }) => void
    onChange({ size: 6 * 1024 * 1024 })
    expect(ElMessage.error).toHaveBeenCalledWith('文件超过 5MB')
  })

  it('超过 1 个文件触发 on-exceed 提示', async () => {
    const w = mountIt()
    await open(w)
    const upload = w.findComponent({ name: 'ElUpload' })
    const onExceed = upload.props('onExceed') as () => void
    onExceed()
    expect(ElMessage.warning).toHaveBeenCalledWith('只能上传 1 个文件')
  })
})
