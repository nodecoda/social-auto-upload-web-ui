import { http } from '@/utils/request'
import request from '@/utils/request'

// 任务管理
export const taskApi = {
  getTasks(params?: Record<string, unknown>) {
    return http.get('/api/v2/tasks', params)
  },
  getTask(taskId: string | number) {
    return http.get(`/api/v2/tasks/${taskId}`)
  },
  createTask(data: unknown) {
    return http.post('/api/v2/tasks', data)
  },
  cancelTask(taskId: string | number) {
    return http.post(`/api/v2/tasks/${taskId}/cancel`)
  },
  retryTask(taskId: string | number) {
    return http.post(`/api/v2/tasks/${taskId}/retry`)
  },
  getQueueStatus() {
    return http.get('/api/v2/queue/status')
  },
}

// 发布历史
export const historyApi = {
  getHistory(params?: Record<string, unknown>) {
    // params: { type?: 'video'|'image', status?, timeRange?, startDate?, endDate?, page, pageSize }
    // 返回: data.items = [{id, type, title, ..., items: [{id, account_name, platform, status, ...}]}, ...]
    return http.get('/api/v2/history', params)
  },
  getBatch(batchId: string | number) {
    return http.get(`/api/v2/history/${batchId}`)
  },
  // 删除单条发布历史
  deleteBatch(batchId: string | number) {
    return http.delete(`/api/v2/history/${batchId}`)
  },
  // 批量删除发布历史 — 走 axios 实例,因为 http.delete 包装会把第二参序列化成 query
  batchDelete(batchIds: Array<string | number>) {
    return request.delete('/api/v2/history/batch', { data: { batch_ids: batchIds } })
  },
}

// 统计数据
export const statsApi = {
  getStats() {
    return http.get('/api/v2/stats')
  },
}

// 系统设置
export const settingsApi = {
  getSettings() {
    return http.get('/api/v2/settings')
  },
  updateSettings(data: unknown) {
    return http.put('/api/v2/settings', data)
  },
}
