import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserStore = defineStore('user', () => {
  const userInfo = ref({
    name: '',
    email: ''
  })
  
  const isLoggedIn = ref(false)
  
  const setUserInfo = (info: any) => {
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