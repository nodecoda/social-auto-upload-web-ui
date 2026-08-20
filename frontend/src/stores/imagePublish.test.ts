import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useImagePublishStore } from './imagePublish'
import { imagePublishApi } from '@/api/imagePublish'
import { ElMessage } from 'element-plus'

vi.mock('@/api/imagePublish', () => ({
  imagePublishApi: {
    uploadImage: vi.fn(),
    saveDraft: vi.fn(),
    publishImage: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

const makeFile = (name = 'a.jpg') => ({ name })

describe('useImagePublishStore', () => {
  let store: any

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useImagePublishStore()
    vi.clearAllMocks()
  })

  it('初始状态: 空列表, publishing=false, currentDraftId=null', () => {
    expect(store.images).toEqual([])
    expect(store.selectedAccounts).toEqual([])
    expect(store.accountConfigs).toEqual({})
    expect(store.publishing).toBe(false)
    expect(store.currentDraftId).toBe(null)
    expect(store.imageCount).toBe(0)
    expect(store.canUpload).toBe(true)
    expect(store.canPublish).toBe(false)
  })

  it('canUpload: 达到 35 张上限后为 false', () => {
    for (let i = 0; i < 35; i++) store.images.push({ url: '', name: `img${i}` })
    expect(store.canUpload).toBe(false)
  })

  it('canPublish: 需要同时有图片和已选账号', () => {
    store.images.push({ url: 'u', name: 'n' })
    expect(store.canPublish).toBe(false)
    store.selectedAccounts.push(1)
    expect(store.canPublish).toBe(true)
  })

  it('upload 成功: 添加占位项, 回调更新 progress, 完成后写 url 和 100', async () => {
    vi.mocked(imagePublishApi.uploadImage).mockImplementation(async (file, onProgress) => {
      onProgress?.(40)
      return { data: { url: 'http://img/ok.jpg' } }
    })
    const res = await store.upload(makeFile('a.jpg'))
    expect(res.data.url).toBe('http://img/ok.jpg')
    expect(store.images).toHaveLength(1)
    expect(store.images[0].name).toBe('a.jpg')
    expect(store.images[0].url).toBe('http://img/ok.jpg')
    expect(store.images[0].progress).toBe(100)
    expect(imagePublishApi.uploadImage).toHaveBeenCalledWith(makeFile('a.jpg'), expect.any(Function))
  })

  it('upload 成功但无 data.url 时回退 res.url', async () => {
    vi.mocked(imagePublishApi.uploadImage).mockResolvedValue({ url: 'http://img/fallback.jpg' })
    await store.upload(makeFile())
    expect(store.images[0].url).toBe('http://img/fallback.jpg')
  })

  it('upload 失败: 移除占位项 + ElMessage.error + 重新抛出', async () => {
    vi.mocked(imagePublishApi.uploadImage).mockRejectedValue(new Error('upload fail'))
    await expect(store.upload(makeFile('bad.jpg'))).rejects.toThrow('upload fail')
    expect(store.images).toEqual([])
    expect(ElMessage.error).toHaveBeenCalledWith('图片 bad.jpg 上传失败')
  })

  it('removeImage: 合法索引移除, 非法索引不操作', () => {
    store.images.push({ name: 'a' }, { name: 'b' }, { name: 'c' })
    store.removeImage(1)
    expect(store.images.map((i: any) => i.name)).toEqual(['a', 'c'])
    store.removeImage(99)
    expect(store.images).toHaveLength(2)
    store.removeImage(-1)
    expect(store.images).toHaveLength(2)
  })

  it('reorder: 向后/向前移动, 非法或相同索引不操作', () => {
    store.images.push({ name: 'a' }, { name: 'b' }, { name: 'c' })
    store.reorder(0, 2)
    expect(store.images.map((i: any) => i.name)).toEqual(['b', 'c', 'a'])
    store.reorder(2, 0)
    expect(store.images.map((i: any) => i.name)).toEqual(['a', 'b', 'c'])
    store.reorder(1, 1)
    store.reorder(9, 0)
    store.reorder(0, -5)
    expect(store.images.map((i: any) => i.name)).toEqual(['a', 'b', 'c'])
  })

  it('replaceImage 成功: 替换条目并写 url/progress', async () => {
    vi.mocked(imagePublishApi.uploadImage).mockResolvedValue({ data: { url: 'http://img/new.jpg' } })
    store.images.push({ url: 'old', name: 'old.jpg', progress: 100 })
    const res = await store.replaceImage(0, makeFile('new.jpg'))
    expect(res.data.url).toBe('http://img/new.jpg')
    expect(store.images[0]).toMatchObject({ url: 'http://img/new.jpg', name: 'new.jpg', progress: 100 })
  })

  it('replaceImage 失败: 恢复原条目 + ElMessage.error + 重新抛出', async () => {
    vi.mocked(imagePublishApi.uploadImage).mockRejectedValue(new Error('boom'))
    store.images.push({ url: 'old', name: 'old.jpg', progress: 100 })
    await expect(store.replaceImage(0, makeFile('new.jpg'))).rejects.toThrow('boom')
    expect(store.images[0]).toEqual({ url: 'old', name: 'old.jpg', progress: 100 })
    expect(ElMessage.error).toHaveBeenCalledWith('图片 new.jpg 上传失败')
  })

  it('replaceImage: 非法索引直接抛错且不调接口', async () => {
    await expect(store.replaceImage(5, makeFile())).rejects.toThrow('无效的图片索引')
    expect(imagePublishApi.uploadImage).not.toHaveBeenCalled()
  })

  it('updateAccountConfig: 新增与合并都保留已有字段', () => {
    store.updateAccountConfig(1, { title: '标题A' })
    expect(store.accountConfigs[1]).toEqual({ title: '标题A' })
    store.updateAccountConfig(1, { description: '描述B' })
    expect(store.accountConfigs[1]).toEqual({ title: '标题A', description: '描述B' })
  })

  it('syncBatchToAll: 批量标题/描述覆盖所有已选账号', () => {
    store.selectedAccounts = [1, 2]
    store.accountConfigs = { 1: { title: '旧', description: '旧d' }, 2: { title: 'x' } }
    store.batchTitle = '批量标题'
    store.batchDescription = '批量描述'
    store.syncBatchToAll()
    expect(store.accountConfigs[1]).toEqual({ title: '批量标题', description: '批量描述' })
    expect(store.accountConfigs[2]).toEqual({ title: '批量标题', description: '批量描述' })
  })

  it('save 成功: 提交 payload, 记录 draftId, 提示保存成功', async () => {
    vi.mocked(imagePublishApi.saveDraft).mockResolvedValue({ data: { id: 'draft-1' } })
    store.images.push({ url: 'u1', name: 'n1' })
    store.selectedAccounts = [1]
    store.accountConfigs = { 1: { title: 't' } }
    store.batchTitle = 'bt'
    store.batchDescription = 'bd'
    const res = await store.save()
    expect(res.data.id).toBe('draft-1')
    expect(store.currentDraftId).toBe('draft-1')
    expect(imagePublishApi.saveDraft).toHaveBeenCalledWith(expect.objectContaining({
      images: [{ url: 'u1', name: 'n1' }],
      selectedAccounts: [1],
      batchTitle: 'bt',
      draftId: null,
    }))
    expect(ElMessage.success).toHaveBeenCalledWith('草稿已保存')
  })

  it('save 失败: ElMessage.error + 重新抛出', async () => {
    vi.mocked(imagePublishApi.saveDraft).mockRejectedValue(new Error('save fail'))
    await expect(store.save()).rejects.toThrow('save fail')
    expect(ElMessage.error).toHaveBeenCalledWith('保存草稿失败')
  })

  it('publish: 无图或无账号时仅 warning 且不发布', async () => {
    const ret = await store.publish()
    expect(ret).toBeUndefined()
    expect(ElMessage.warning).toHaveBeenCalledWith('请至少上传一张图片并选择一个账号')
    expect(imagePublishApi.publishImage).not.toHaveBeenCalled()
    expect(store.publishing).toBe(false)
  })

  it('publish 成功(立即): payload 无 scheduledAt, 提示提交, publishing 复位', async () => {
    vi.mocked(imagePublishApi.publishImage).mockResolvedValue({})
    store.images.push({ url: 'u1', name: 'n1' })
    store.selectedAccounts = [1]
    store.accountConfigs = { 1: { title: 't' } }
    await store.publish()
    expect(imagePublishApi.publishImage).toHaveBeenCalledWith(expect.objectContaining({
      images: [{ url: 'u1', name: 'n1' }],
      selectedAccounts: [1],
      scheduledAt: null,
    }))
    expect(ElMessage.success).toHaveBeenCalledWith('发布任务已提交')
    expect(store.publishing).toBe(false)
  })

  it('publish 定时: payload 带 scheduledAt, 提示定时发布', async () => {
    vi.mocked(imagePublishApi.publishImage).mockResolvedValue({})
    store.images.push({ url: 'u', name: 'n' })
    store.selectedAccounts = [1]
    await store.publish('2026-09-01 10:00:00')
    expect(imagePublishApi.publishImage).toHaveBeenCalledWith(expect.objectContaining({
      scheduledAt: '2026-09-01 10:00:00',
    }))
    expect(ElMessage.success).toHaveBeenCalledWith('已设置定时发布')
  })

  it('publish 失败: ElMessage.error + 重新抛出 + publishing 复位', async () => {
    vi.mocked(imagePublishApi.publishImage).mockRejectedValue(new Error('publish fail'))
    store.images.push({ url: 'u', name: 'n' })
    store.selectedAccounts = [1]
    await expect(store.publish()).rejects.toThrow('publish fail')
    expect(ElMessage.error).toHaveBeenCalledWith('发布失败')
    expect(store.publishing).toBe(false)
  })

  it('reset: 清空全部状态', () => {
    store.images.push({ url: 'u', name: 'n' })
    store.selectedAccounts = [1]
    store.accountConfigs = { 1: { title: 't' } }
    store.currentDraftId = 'draft-9'
    store.publishing = true
    store.batchTitle = 'bt'
    store.batchDescription = 'bd'
    store.reset()
    expect(store.images).toEqual([])
    expect(store.selectedAccounts).toEqual([])
    expect(store.accountConfigs).toEqual({})
    expect(store.currentDraftId).toBe(null)
    expect(store.publishing).toBe(false)
    expect(store.batchTitle).toBe('')
    expect(store.batchDescription).toBe('')
  })
})
