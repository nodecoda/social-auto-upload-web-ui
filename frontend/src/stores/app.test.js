import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAppStore } from './app'
import { settingsApi } from '@/api/v2'

vi.mock('@/api/v2', () => ({
  settingsApi: {
    updateSettings: vi.fn(),
  },
}))

describe('useAppStore', () => {
  let store

  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark', 'light')
    setActivePinia(createPinia())
    store = useAppStore()
    vi.clearAllMocks()
  })

  it('初始状态: 默认值 (无 localStorage)', () => {
    expect(store.isFirstTimeAccountManagement).toBe(true)
    expect(store.isFirstTimeMaterialManagement).toBe(true)
    expect(store.autoFillTitle).toBe(true)
    expect(store.autoSaveDraft).toBe(true)
    expect(store.autoSaveInterval).toBe(10)
    expect(store.accountCheckMode).toBe('pre-publish')
    expect(store.theme).toBe('dark')
    expect(store.disabledPlatforms).toEqual([])
    expect(store.isAccountRefreshing).toBe(false)
  })

  it('setAutoFillTitle 更新状态并持久化到 localStorage', () => {
    store.setAutoFillTitle(false)
    expect(store.autoFillTitle).toBe(false)
    const saved = JSON.parse(localStorage.getItem('app_settings'))
    expect(saved.autoFillTitle).toBe(false)
  })

  it('loadAutoFillTitle: 读取持久化值, 无值时回退默认 true', () => {
    store.setAutoFillTitle(false)
    expect(store.autoFillTitle).toBe(false)
    // 模拟重新初始化
    store.autoFillTitle = true
    store.loadAutoFillTitle()
    expect(store.autoFillTitle).toBe(false)
    localStorage.clear()
    store.autoFillTitle = false
    store.loadAutoFillTitle()
    expect(store.autoFillTitle).toBe(true)
  })

  it('setAutoSaveDraft / setAutoSaveInterval 更新状态并持久化', () => {
    store.setAutoSaveDraft(false)
    store.setAutoSaveInterval(30)
    expect(store.autoSaveDraft).toBe(false)
    expect(store.autoSaveInterval).toBe(30)
    const saved = JSON.parse(localStorage.getItem('app_settings'))
    expect(saved.autoSaveDraft).toBe(false)
    expect(saved.autoSaveInterval).toBe(30)
  })

  it('loadAutoSaveSettings: 读取持久化值, 无值时回退默认', () => {
    store.setAutoSaveDraft(false)
    store.setAutoSaveInterval(20)
    store.autoSaveDraft = true
    store.autoSaveInterval = 10
    store.loadAutoSaveSettings()
    expect(store.autoSaveDraft).toBe(false)
    expect(store.autoSaveInterval).toBe(20)
    localStorage.clear()
    store.loadAutoSaveSettings()
    expect(store.autoSaveDraft).toBe(true)
    expect(store.autoSaveInterval).toBe(10)
  })

  it('访问状态: 设置已访问 + 重置', () => {
    store.setAccountManagementVisited()
    store.setMaterialManagementVisited()
    expect(store.isFirstTimeAccountManagement).toBe(false)
    expect(store.isFirstTimeMaterialManagement).toBe(false)
    store.resetVisitStatus()
    expect(store.isFirstTimeAccountManagement).toBe(true)
    expect(store.isFirstTimeMaterialManagement).toBe(true)
  })

  it('setMaterials / removeMaterial: 命中删除, 未命中不变', () => {
    store.setMaterials([{ id: 1 }, { id: 2 }])
    expect(store.materials).toHaveLength(2)
    store.removeMaterial(1)
    expect(store.materials).toEqual([{ id: 2 }])
    store.removeMaterial(99)
    expect(store.materials).toHaveLength(1)
  })

  it('setAccountRefreshing 更新刷新状态', () => {
    store.setAccountRefreshing(true)
    expect(store.isAccountRefreshing).toBe(true)
    store.setAccountRefreshing(false)
    expect(store.isAccountRefreshing).toBe(false)
  })

  it('isPlatformDisabled 判断黑名单', () => {
    store.disabledPlatforms = ['xiaohongshu', 'youtube']
    expect(store.isPlatformDisabled('xiaohongshu')).toBe(true)
    expect(store.isPlatformDisabled('bilibili')).toBe(false)
  })

  it('addDisabledPlatforms: 去重后调 API 并更新状态', async () => {
    store.disabledPlatforms = ['xiaohongshu']
    settingsApi.updateSettings.mockResolvedValue({})
    await store.addDisabledPlatforms(['xiaohongshu', 'youtube'])
    expect(store.disabledPlatforms).toEqual(['xiaohongshu', 'youtube'])
    expect(settingsApi.updateSettings).toHaveBeenCalledWith({
      disabledPlatforms: ['xiaohongshu', 'youtube'],
    })
  })

  it('addDisabledPlatforms: 全部重复时不调 API', async () => {
    store.disabledPlatforms = ['xiaohongshu']
    await store.addDisabledPlatforms(['xiaohongshu'])
    expect(settingsApi.updateSettings).not.toHaveBeenCalled()
  })

  it('addDisabledPlatforms: API 失败时回滚状态并重新抛出', async () => {
    settingsApi.updateSettings.mockRejectedValue(new Error('api down'))
    await expect(store.addDisabledPlatforms(['youtube'])).rejects.toThrow('api down')
    expect(store.disabledPlatforms).toEqual([])
  })

  it('removeDisabledPlatform: 成功移除并调 API', async () => {
    store.disabledPlatforms = ['xiaohongshu', 'youtube']
    settingsApi.updateSettings.mockResolvedValue({})
    await store.removeDisabledPlatform('xiaohongshu')
    expect(store.disabledPlatforms).toEqual(['youtube'])
    expect(settingsApi.updateSettings).toHaveBeenCalledWith({
      disabledPlatforms: ['youtube'],
    })
  })

  it('removeDisabledPlatform: API 失败时回滚并重新抛出', async () => {
    store.disabledPlatforms = ['xiaohongshu']
    settingsApi.updateSettings.mockRejectedValue(new Error('api down'))
    await expect(store.removeDisabledPlatform('xiaohongshu')).rejects.toThrow('api down')
    expect(store.disabledPlatforms).toEqual(['xiaohongshu'])
  })

  it('setAccountCheckMode / loadAccountCheckMode 读写持久化', () => {
    store.setAccountCheckMode('startup')
    expect(store.accountCheckMode).toBe('startup')
    store.accountCheckMode = 'pre-publish'
    store.loadAccountCheckMode()
    expect(store.accountCheckMode).toBe('startup')
  })

  it('setTheme: 更新状态 + 同步 html class + 持久化', () => {
    store.setTheme('light')
    expect(store.theme).toBe('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(JSON.parse(localStorage.getItem('app_settings')).theme).toBe('light')
  })

  it('toggleTheme: dark ↔ light 切换', () => {
    store.toggleTheme()
    expect(store.theme).toBe('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
    store.toggleTheme()
    expect(store.theme).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('loadTheme: 读取持久化主题, 无值回退 dark', () => {
    store.setTheme('light')
    store.theme = 'dark'
    store.loadTheme()
    expect(store.theme).toBe('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
    localStorage.clear()
    store.theme = 'light'
    store.loadTheme()
    expect(store.theme).toBe('dark')
  })
})
