import { http } from '@/utils/request'
import { materialsApi } from '@/api/materials'

export const imagePublishApi = {
  uploadImage(file: File, onProgress?: (percent: number) => void): Promise<{ data?: { url?: string }; url?: string }> {
    const formData = new FormData()
    formData.append('file', file)
    return materialsApi.upload(formData, (percent: number) => {
      if (onProgress) {
        onProgress(percent)
      }
    }) as Promise<{ data?: { url?: string }; url?: string }>
  },
  publishImage(data: unknown) { return http.post('/api/image-publish/publish', data) },
  getDrafts() { return http.get('/api/image-publish/drafts') },
  saveDraft(data: unknown): Promise<{ data?: { id?: string | number } }> { return http.post('/api/image-publish/drafts', data) },
  deleteDraft(id: string | number) { return http.delete(`/api/image-publish/drafts/${id}`) },
  getHistory() { return http.get('/api/image-publish/history') },
  // 草稿批量发布（图文明文）：POST /api/image-publish/drafts/batch-publish
  batchPublishImageDrafts(draftIds: Array<string | number>) {
    return http.post('/api/image-publish/drafts/batch-publish', { draft_ids: draftIds })
  },
}
