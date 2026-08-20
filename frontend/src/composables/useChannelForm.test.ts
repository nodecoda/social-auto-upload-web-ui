import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, reactive } from 'vue'
import { useChannelForm } from './useChannelForm'

const DEFAULTS = {
  title: '',
  description: '',
  tags: [],
  scheduleTime: '',
  isOriginal: false,
  enableTimer: 0,
}

function setup(accountId: number | null = null, extra = {}) {
  const props = reactive({ accountId, disabled: false })
  const emit = vi.fn()
  const api = useChannelForm(DEFAULTS, { props, emit }, extra)
  return { props, emit, ...api }
}

describe('useChannelForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('初始化: form 深拷贝 defaults, platformConfig 为 defaults', () => {
    const { form, platformConfig } = setup()
    expect(form).toEqual(DEFAULTS)
    expect(platformConfig).toEqual(DEFAULTS)
    expect(form).not.toBe(platformConfig)
  })

  it('初始 watch 立即应用 platformConfig 到 form', () => {
    const { form } = setup(1)
    expect(form).toEqual(DEFAULTS)
  })

  it('切换 accountId: form 应用该账号的合并配置', async () => {
    const { props, accountOverrides, form } = setup()
    accountOverrides[5] = { title: '账号标题' }
    props.accountId = 5
    await nextTick()
    expect(form.title).toBe('账号标题')
    expect(form.description).toBe('')
  })

  it('无 accountId 时修改 form → 同步到 platformConfig 并 emit', async () => {
    const { form, platformConfig, emit } = setup()
    form.title = '新标题'
    form.tags = ['a', 'b']
    await nextTick()
    expect(platformConfig.title).toBe('新标题')
    expect(platformConfig.tags).toEqual(['a', 'b'])
    expect(emit).toHaveBeenCalledWith('config-changed')
  })

  it('有 accountId 时修改 form → 写入 accountOverrides diff', async () => {
    const { props, accountOverrides, form } = setup(7)
    form.title = '覆盖标题'
    await nextTick()
    expect(accountOverrides[7].title).toBe('覆盖标题')
    expect(accountOverrides[7].description).toBeUndefined()
  })

  it('有 accountId 时改回 platformConfig 值 → 删除该 override', async () => {
    const { props, accountOverrides, form, platformConfig } = setup(7)
    form.title = '临时改'
    await nextTick()
    expect(accountOverrides[7].title).toBe('临时改')
    form.title = platformConfig.title  // 回到默认 ''
    await nextTick()
    expect(accountOverrides[7]).toBeUndefined()
  })

  it('getMergedConfig: override 覆盖 platformConfig, 数组字段深拷贝', () => {
    const { accountOverrides, getMergedConfig, platformConfig } = setup(3)
    platformConfig.tags = ['默认标签']
    accountOverrides[3] = { title: '覆盖', tags: ['覆盖标签'] }
    const merged = getMergedConfig(3)
    expect(merged.title).toBe('覆盖')
    expect(merged.tags).toEqual(['覆盖标签'])
    expect(merged.tags).not.toBe(accountOverrides[3].tags)
    expect(merged.description).toBe('')
    // 无 override 的账号回退 platformConfig 且不共享数组引用
    const plain = getMergedConfig(99)
    expect(plain.tags).toEqual(['默认标签'])
    expect(plain.tags).not.toBe(platformConfig.tags)
  })

  it('hasAccountOverride: 仅"有意义"的 override 返回 true', () => {
    const { hasAccountOverride, accountOverrides } = setup()
    accountOverrides[1] = { title: 'x' }
    expect(hasAccountOverride(1)).toBe(true)
    accountOverrides[2] = { tags: [] }
    expect(hasAccountOverride(2)).toBe(false)
  })

  it('resetOverride: 删除 override 并恢复 form 为 platformConfig', async () => {
    const { props, accountOverrides, form, resetOverride, emit } = setup(4)
    accountOverrides[4] = { title: '覆盖' }
    form.title = '覆盖'
    await nextTick()
    resetOverride()
    expect(accountOverrides[4]).toBeUndefined()
    expect(form.title).toBe('')
    expect(emit).toHaveBeenCalledWith('config-changed')
  })

  it('publicApi.publish: 调用 publishFn 并传入合并配置', async () => {
    const publishFn = vi.fn().mockResolvedValue(undefined)
    const { publicApi, accountOverrides } = setup(8, { publishFn })
    accountOverrides[8] = { title: '覆盖标题' }
    await publicApi.publish(8, '账号名', { images: [{ id: 1 }] }, { batchId: 'b1' })
    expect(publishFn).toHaveBeenCalledWith(8, '账号名', { images: [{ id: 1 }] }, expect.objectContaining({ title: '覆盖标题' }), { batchId: 'b1' })
  })

  it('publicApi.publish: 无 publishFn 时不抛错', async () => {
    const { publicApi } = setup()
    await expect(publicApi.publish(1, 'n', { images: [] }, {})).resolves.toBeUndefined()
  })

  it('publicApi.getConfigs: 返回序列化深拷贝', () => {
    const { publicApi, platformConfig, accountOverrides } = setup()
    platformConfig.title = '平台标题'
    accountOverrides[2] = { title: '账号标题' }
    const { platformConfig: pc, accountOverrides: ao } = publicApi.getConfigs()
    expect(pc).toEqual({ ...DEFAULTS, title: '平台标题' })
    expect(ao).toEqual({ 2: { title: '账号标题' } })
    // 修改返回值不影响内部状态
    pc.title = '外部改'
    expect(platformConfig.title).toBe('平台标题')
  })

  it('publicApi.restoreConfigs: 恢复 platformConfig + overrides 并应用 form', async () => {
    const { props, publicApi, form, platformConfig, accountOverrides } = setup(1)
    publicApi.restoreConfigs({ title: '恢复标题' }, { 1: { title: '账号恢复' } })
    await nextTick()
    expect(platformConfig.title).toBe('恢复标题')
    expect(accountOverrides[1]).toEqual({ title: '账号恢复' })
    expect(form.title).toBe('账号恢复')  // 当前账号应用 override
  })

  it('publicApi.syncTitle/syncDescription/syncTags: 无账号时写 platformConfig + form 并 emit', async () => {
    const { publicApi, platformConfig, form, emit } = setup()
    publicApi.syncTitle('同步标题')
    publicApi.syncDescription('同步描述')
    publicApi.syncTags(['t1'])
    await nextTick()
    expect(platformConfig.title).toBe('同步标题')
    expect(form.title).toBe('同步标题')
    expect(platformConfig.description).toBe('同步描述')
    expect(platformConfig.tags).toEqual(['t1'])
    expect(emit).toHaveBeenCalledWith('config-changed')
  })

  it('publicApi.syncTitle: 有账号时仅 emit, 不写 platformConfig', async () => {
    const { publicApi, platformConfig, emit } = setup(9)
    publicApi.syncTitle('不应写入')
    expect(platformConfig.title).toBe('')
    expect(emit).toHaveBeenCalledWith('config-changed')
  })

  it('publicApi.validate: 默认校验标题非空', () => {
    const { publicApi } = setup()
    expect(publicApi.validate(1)).toEqual({ valid: false, errors: ['标题不能为空'] })
    const pub2 = setup().publicApi
    pub2.setPlatformConfig({ title: '有标题' })
    expect(pub2.validate(1).valid).toBe(true)
  })

  it('publicApi.validate: 有 validateFn 时代理并传 merged', () => {
    const validateFn = vi.fn(() => ({ valid: true, errors: [] }))
    const { publicApi } = setup(5, { validateFn })
    publicApi.validate(5)
    expect(validateFn).toHaveBeenCalledWith(5, expect.objectContaining({ title: '' }))
  })

  it('publicApi.setPlatformConfig: 更新 platformConfig + form, undefined 跳过', async () => {
    const { publicApi, platformConfig, form, emit } = setup()
    publicApi.setPlatformConfig({ title: '新平台标题', tags: ['a'], scheduleTime: undefined })
    expect(platformConfig.title).toBe('新平台标题')
    expect(platformConfig.tags).toEqual(['a'])
    expect(form.title).toBe('新平台标题')
    expect(form.tags).toEqual(['a'])
    expect(emit).toHaveBeenCalledWith('config-changed')
  })

  it('publicApi.setAccountOverride: 设置/删除 override, 当前账号时同步 form', async () => {
    const { props, publicApi, accountOverrides, form } = setup(6)
    publicApi.setAccountOverride(6, { title: '账号6' })
    expect(accountOverrides[6].title).toBe('账号6')
    expect(form.title).toBe('账号6')  // 当前账号 applyToForm
    // 空 partial 为 no-op: 保留已有 override
    publicApi.setAccountOverride(6, {})
    expect(accountOverrides[6]).toEqual({ title: '账号6' })
    // 字段置空(无意义值) → 删除 override
    publicApi.setAccountOverride(6, { title: '' })
    expect(accountOverrides[6]).toBeUndefined()
  })

  it('publicApi.getCheckedAccountIds: 仅返回有意义 override 的账号数字 id', () => {
    const { publicApi, accountOverrides } = setup()
    accountOverrides[5] = { title: 'x' }
    accountOverrides[6] = { tags: [] }
    accountOverrides[7] = { description: 'd' }
    expect(publicApi.getCheckedAccountIds()).toEqual([5, 7])
  })
})
