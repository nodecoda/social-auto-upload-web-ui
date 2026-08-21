import { http } from '@/utils/request'

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
  batchDeleteDrafts(draftIds: Array<string | number>) {
    return http.delete('/api/v2/drafts/batch', undefined, { draft_ids: draftIds })
  },
}
