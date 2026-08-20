import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ElMessage } from 'element-plus'

const httpPost = vi.fn()
vi.mock('@/utils/request', () => ({
  http: { post: (...args: unknown[]) => httpPost(...args) },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

import StorageSettingsCard, { type StorageConfig } from './StorageSettingsCard.vue'

const ElInput = {
  props: ['modelValue', 'placeholder'],
  template: '<input :value="modelValue" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value)" />',
}

const ElRadioGroup = {
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<div class="radio-group-stub"><slot /></div>',
}

const ElRadio = {
  props: ['value'],
  template: '<label class="radio-stub">{{ $slots.default ? $slots.default()[0].children : value }}</label>',
}

const localStorage: StorageConfig = {
  type: 'local',
  s3: { endpoint: '', access_key: '', secret_key: '', bucket: '', region: '' },
}

const s3Storage: StorageConfig = {
  type: 's3',
  s3: { endpoint: 'http://127.0.0.1:9000', access_key: 'ak', secret_key: 'sk', bucket: 'bk', region: 'cn-east-1' },
}

const mountIt = (storage: StorageConfig) =>
  mount(StorageSettingsCard, {
    props: { storage },
    global: { stubs: { ElInput, ElRadioGroup, ElRadio } },
  })

describe('StorageSettingsCard', () => {
  beforeEach(() => {
    httpPost.mockReset()
    vi.mocked(ElMessage.success).mockClear()
    vi.mocked(ElMessage.error).mockClear()
  })

  it('renders title and storage type options', () => {
    const w = mountIt(localStorage)
    expect(w.text()).toContain('文件存储')
    expect(w.text()).toContain('本地存储')
    expect(w.text()).toContain('S3 兼容存储')
  })

  it('hides S3 fields when type is local', () => {
    const w = mountIt(localStorage)
    expect(w.text()).not.toContain('Endpoint')
    expect(w.text()).not.toContain('Access Key')
    expect(w.findAll('.setting-row')).toHaveLength(1)
  })

  it('shows all S3 fields when type is s3', () => {
    const w = mountIt(s3Storage)
    expect(w.text()).toContain('Endpoint')
    expect(w.text()).toContain('Access Key')
    expect(w.text()).toContain('Secret Key')
    expect(w.text()).toContain('Bucket')
    expect(w.text()).toContain('Region')
    expect(w.text()).toContain('连接测试')
    expect(w.findAll('.setting-row').length).toBeGreaterThanOrEqual(7)
  })

  it('edits s3 endpoint through shared object reference', async () => {
    const w = mountIt(s3Storage)
    await w.find('input[placeholder="http://127.0.0.1:9000"]').setValue('http://localhost:9000')
    expect(s3Storage.s3.endpoint).toBe('http://localhost:9000')
  })

  it('calls test-s3 api and shows success message', async () => {
    httpPost.mockResolvedValue({ code: 200, msg: 'ok' })
    const w = mountIt(s3Storage)
    const btn = w.find('button.cache-btn')
    await btn.trigger('click')
    expect(httpPost).toHaveBeenCalledWith('/api/materials/test-s3', s3Storage.s3)
    await vi.waitFor(() => expect(vi.mocked(ElMessage.success)).toHaveBeenCalledWith('S3 连接成功'))
    expect(w.find('button.cache-btn').text()).toBe('测试连接')
  })

  it('shows error message when test-s3 fails', async () => {
    httpPost.mockResolvedValue({ code: 500, msg: 'boom' })
    const w = mountIt(s3Storage)
    await w.find('button.cache-btn').trigger('click')
    await vi.waitFor(() => expect(vi.mocked(ElMessage.error)).toHaveBeenCalledWith('boom'))
  })
})
