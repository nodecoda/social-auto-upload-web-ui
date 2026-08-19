import { describe, it, expect } from 'vitest'
import pinia, { useUserStore, useAccountStore, useAppStore } from './index'

describe('stores/index', () => {
  it('默认导出为 Pinia 实例', () => {
    expect(pinia).toBeTruthy()
    expect(typeof pinia.install).toBe('function')
  })

  it('命名导出三个 store 工厂函数', () => {
    expect(typeof useUserStore).toBe('function')
    expect(typeof useAccountStore).toBe('function')
    expect(typeof useAppStore).toBe('function')
    expect(useUserStore.$id).toBe('user')
    expect(useAccountStore.$id).toBe('account')
    expect(useAppStore.$id).toBe('app')
  })
})
