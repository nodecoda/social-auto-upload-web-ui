import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick, defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { useAppStore } from '@/stores/app'
import { useAutoSave } from './useAutoSave'

describe('useAutoSave', () => {
  let store: ReturnType<typeof useAppStore>

  let warnSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    store = useAppStore()
    // 直接调用 composable 时 Vue 会警告 onBeforeUnmount 无组件实例; 测试本身不受影响
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    warnSpy.mockRestore()
    vi.useRealTimers()
  })

  it('autoSaveDraft=false 时不启动定时器', () => {
    store.setAutoSaveDraft(false)
    const saveFn = vi.fn()
    const { hasChanges, startAutoSaveTimer } = useAutoSave(saveFn)
    hasChanges.value = true
    startAutoSaveTimer()
    vi.advanceTimersByTime(60 * 1000)
    expect(saveFn).not.toHaveBeenCalled()
  })

  it('到间隔且有变更时触发 saveFn 并复位 hasChanges', () => {
    store.setAutoSaveInterval(10)
    const saveFn = vi.fn()
    const { hasChanges, startAutoSaveTimer } = useAutoSave(saveFn)
    hasChanges.value = true
    startAutoSaveTimer()
    vi.advanceTimersByTime(10 * 1000)
    expect(saveFn).toHaveBeenCalledTimes(1)
    expect(hasChanges.value).toBe(false)
  })

  it('间隔未到或 hasChanges=false 时不触发 saveFn', () => {
    store.setAutoSaveInterval(10)
    const saveFn = vi.fn()
    const { hasChanges, startAutoSaveTimer } = useAutoSave(saveFn)
    startAutoSaveTimer()
    vi.advanceTimersByTime(9 * 1000)
    expect(saveFn).not.toHaveBeenCalled()
    hasChanges.value = true
    vi.advanceTimersByTime(20 * 1000)
    expect(saveFn).toHaveBeenCalledTimes(1)
    // hasChanges 已复位, 下一周期不再触发
    vi.advanceTimersByTime(10 * 1000)
    expect(saveFn).toHaveBeenCalledTimes(1)
  })

  it('重复 startAutoSaveTimer 不会叠加多个 interval', () => {
    store.setAutoSaveInterval(5)
    const saveFn = vi.fn()
    const { hasChanges, startAutoSaveTimer } = useAutoSave(saveFn)
    hasChanges.value = true
    startAutoSaveTimer()
    startAutoSaveTimer()
    startAutoSaveTimer()
    vi.advanceTimersByTime(5 * 1000)
    expect(saveFn).toHaveBeenCalledTimes(1)
  })

  it('stopAutoSaveTimer 停止后不再触发', () => {
    store.setAutoSaveInterval(10)
    const saveFn = vi.fn()
    const { hasChanges, startAutoSaveTimer, stopAutoSaveTimer } = useAutoSave(saveFn)
    hasChanges.value = true
    startAutoSaveTimer()
    stopAutoSaveTimer()
    vi.advanceTimersByTime(30 * 1000)
    expect(saveFn).not.toHaveBeenCalled()
  })

  it('watch autoSaveDraft: 关闭时停止, 重新开启时启动', async () => {
    store.setAutoSaveInterval(10)
    const saveFn = vi.fn()
    const { hasChanges } = useAutoSave(saveFn)
    hasChanges.value = true
    store.setAutoSaveDraft(false)
    await nextTick()
    vi.advanceTimersByTime(30 * 1000)
    expect(saveFn).not.toHaveBeenCalled()
    store.setAutoSaveDraft(true)
    await nextTick()
    vi.advanceTimersByTime(10 * 1000)
    expect(saveFn).toHaveBeenCalledTimes(1)
  })

  it('watch autoSaveInterval: 间隔变化后按新间隔重启', async () => {
    store.setAutoSaveInterval(10)
    const saveFn = vi.fn()
    const { hasChanges } = useAutoSave(saveFn)
    hasChanges.value = true
    vi.advanceTimersByTime(9 * 1000)
    expect(saveFn).not.toHaveBeenCalled()
    store.setAutoSaveInterval(2)
    await nextTick()
    vi.advanceTimersByTime(2 * 1000)
    expect(saveFn).toHaveBeenCalledTimes(1)
  })

  it('组件卸载时清理定时器, 不再触发 saveFn', () => {
    store.setAutoSaveInterval(10)
    const saveFn = vi.fn()
    const Host = defineComponent({
      setup() {
        const api = useAutoSave(saveFn)
        return api
      },
      template: '<div />',
    })
    const wrapper = mount(Host, { global: { plugins: [createPinia()] } })
    wrapper.vm.hasChanges = true
    wrapper.vm.startAutoSaveTimer()
    vi.advanceTimersByTime(10 * 1000)
    expect(saveFn).toHaveBeenCalledTimes(1)
    saveFn.mockClear()
    wrapper.unmount()
    vi.advanceTimersByTime(30 * 1000)
    expect(saveFn).not.toHaveBeenCalled()
  })
})
