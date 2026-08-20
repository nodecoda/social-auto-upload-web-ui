import { http } from '@/utils/request'

// 账号管理相关API
export const accountApi = {
  // 获取有效账号列表（带验证）
  getValidAccounts() {
    return http.get('/getValidAccounts')
  },

  // 获取账号列表（不带验证，快速加载）
  getAccounts() {
    return http.get('/getAccounts')
  },

  // 添加账号
  addAccount(data: unknown) {
    return http.post('/account', data)
  },

  // 更新账号
  updateAccount(data: unknown) {
    return http.post('/updateUserinfo', data)
  },

  // 删除账号（DELETE，带副作用操作不走 GET）
  deleteAccount(id: string | number) {
    return http.delete(`/deleteAccount?id=${id}`)
  },

  // 同步账号资料（头像+昵称）
  syncProfile(id: string | number) {
    return http.post('/syncProfile', { id })
  },

  // ── 标签管理 ──
  getTags(): Promise<{ code?: number; data?: unknown }> {
    return http.get('/api/tags')
  },

  createTag(data: unknown) {
    return http.post('/api/tags', data)
  },

  deleteTag(id: string | number) {
    return http.delete(`/api/tags/${id}`)
  },

  setAccountTags(accountId: string | number, tagIds: Array<string | number>) {
    return http.put(`/api/accounts/${accountId}/tags`, { tag_ids: tagIds })
  },

  setBatchAccountTags(accountIds: Array<string | number>, tagIds: Array<string | number>) {
    return http.put('/api/accounts/batch/tags', {
      account_ids: accountIds,
      tag_ids: tagIds
    })
  },

  getAccountTags(accountId: string | number) {
    return http.get(`/api/accounts/${accountId}/tags`)
  },

  // ── cookie 字符串导入账号 ──

  // 列出所有支持 cookie 导入的平台
  getImportSupportedPlatforms() {
    return http.get('/platforms/import-supported')
  },

  // 启动一个 cookie 导入任务，返回 task_id
  startImportAccount(data: unknown) {
    return http.post('/importAccount', data)
  },
}