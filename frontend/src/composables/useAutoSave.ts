import { ref, watch, onBeforeUnmount, type Ref } from 'vue'
import { useAppStore } from '@/stores/app'

export function useAutoSave(saveFn: () => void): { hasChanges: Ref<boolean>; startAutoSaveTimer: () => void; stopAutoSaveTimer: () => void } {
  const appStore = useAppStore()
  const autoSaveTimer = ref<ReturnType<typeof setInterval> | null>(null)
  const hasChanges = ref(false)

  function startAutoSaveTimer() {
    stopAutoSaveTimer()
    if (!appStore.autoSaveDraft) return
    autoSaveTimer.value = setInterval(() => {
      if (hasChanges.value) {
        saveFn()
        hasChanges.value = false
      }
    }, appStore.autoSaveInterval * 1000)
  }

  function stopAutoSaveTimer() {
    if (autoSaveTimer.value) {
      clearInterval(autoSaveTimer.value)
      autoSaveTimer.value = null
    }
  }

  watch(() => appStore.autoSaveDraft, (val) => {
    if (val) startAutoSaveTimer()
    else stopAutoSaveTimer()
  })

  watch(() => appStore.autoSaveInterval, () => {
    if (appStore.autoSaveDraft) startAutoSaveTimer()
  })

  onBeforeUnmount(() => {
    stopAutoSaveTimer()
  })

  return {
    hasChanges,
    startAutoSaveTimer,
    stopAutoSaveTimer,
  }
}
