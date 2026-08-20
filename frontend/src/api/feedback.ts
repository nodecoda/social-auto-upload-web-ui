import { http } from '@/utils/request'

export function listFeedback({ status, includeAll = false, page = 1, pageSize = 20 }: { status?: string | number | null; includeAll?: boolean; page?: number; pageSize?: number }) {
  const params: Record<string, unknown> = { page, page_size: pageSize }
  if (status !== undefined && status !== null) {
    params.status = status
  } else if (includeAll) {
    params.include_all = 'true'
  }
  return http.get('/api/feedback/list', params)
}

export function submitFeedback(formData: FormData) {
  return http.upload('/api/feedback/submit', formData)
}

export function voteFeedback({ id }: { id: string | number }) {
  return http.post('/api/feedback/vote', { id })
}
