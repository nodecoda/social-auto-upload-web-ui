import { http } from '@/utils/request'
import request from '@/utils/request'

export const draftApi = {
  getDrafts(type?: string) {
    const params = type ? `?type=${type}` : ''
    return http.get(`/api/v2/drafts${params}`)
  },
  createDraft(data: unknown) {
    return http.post('/api/v2/drafts', data)
  },
  getDraft(id: string | number) {
    return http.get(`/api/v2/drafts/${id}`)
  },
  updateDraft(id: string | number, data: unknown) {
    return http.put(`/api/v2/drafts/${id}`, data)
  },
  deleteDraft(id: string | number) {
    return http.delete(`/api/v2/drafts/${id}`)
  },
  // 草稿批量发布（视频）
  batchPublishVideoDrafts(draftIds: Array<string | number>) {
    return http.post('/api/v2/drafts/batch-publish', { draft_ids: draftIds })
  },
  // 草稿批量删除 — 走 axios 实例,因为 http.delete 包装会把第二参序列化成 query
  batchDeleteDrafts(draftIds: Array<string | number>) {
    return request.delete('/api/v2/drafts/batch', { data: { draft_ids: draftIds } })
  },
}
