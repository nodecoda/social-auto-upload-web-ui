import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface UserInfo {
  name: string
  email: string
}

export const useUserStore = defineStore('user', () => {
  const userInfo = ref<UserInfo>({
    name: '',
    email: ''
  })
  
  const isLoggedIn = ref(false)
  
  const setUserInfo = (info: UserInfo) => {
    userInfo.value = info
    isLoggedIn.value = true
  }
  
  const logout = () => {
    userInfo.value = {
      name: '',
      email: ''
    }
    isLoggedIn.value = false
  }
  
  return {
    userInfo,
    isLoggedIn,
    setUserInfo,
    logout
  }
})