// 反馈卡片/详情抽屉共享的类型与纯函数（F2b 拆分后由 FeedbackCard 与 Feedback.vue 共用）

export interface FeedbackAttachment {
  id: number
  file_url: string
}

export interface FeedbackItem {
  id: number
  status: number
  content: string
  email: string
  created_at: string
  vote_count?: number
  assignee?: string
  attachments?: FeedbackAttachment[]
}

export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

export function statusLabel(s: number) {
  return { 1: '待确认', 2: '处理中', 3: '已完成', 4: '已拒绝' }[s] || '未知'
}
export function statusTagType(s: number): TagType {
  const map: Record<number, TagType> = { 1: 'warning', 2: 'primary', 3: 'success', 4: 'info' }
  return map[s] || 'info'
}
export function truncate(text: string, n: number) {
  if (!text) return ''
  return text.length > n ? text.slice(0, n) + '…' : text
}
export function maskEmail(email: string) {
  if (!email) return ''
  const [user, domain] = email.split('@')
  if (!domain) return email
  return user.slice(0, 2) + '***@' + domain
}
export function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}
