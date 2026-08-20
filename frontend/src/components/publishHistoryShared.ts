// PublishHistoryDetail 视图与拆分子组件共享的纯函数（F2d）

export function statusLabel(status: string): string {
  return ({
    pending: '等待中',
    running: '发布中',
    success: '全部成功',
    partial: '部分失败',
    failed: '全部失败',
    cancelled: '已取消',
  }[status] || status)
}

export function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function formatDuration(s: number | null | undefined): string {
  if (s == null) return ''
  if (s < 60) return `${s}秒`
  return `${Math.floor(s / 60)}分${s % 60}秒`
}
