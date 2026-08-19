import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUserStore } from './user'

describe('useUserStore', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useUserStore()
  })

  it('初始状态: 空用户信息且未登录', () => {
    expect(store.userInfo).toEqual({ name: '', email: '' })
    expect(store.isLoggedIn).toBe(false)
  })

  it('setUserInfo 写入用户信息并标记已登录', () => {
    store.setUserInfo({ name: 'admin', email: 'a@b.com' })
    expect(store.userInfo).toEqual({ name: 'admin', email: 'a@b.com' })
    expect(store.isLoggedIn).toBe(true)
  })

  it('logout 清空用户信息并标记未登录', () => {
    store.setUserInfo({ name: 'admin', email: 'a@b.com' })
    store.logout()
    expect(store.userInfo).toEqual({ name: '', email: '' })
    expect(store.isLoggedIn).toBe(false)
  })
})
