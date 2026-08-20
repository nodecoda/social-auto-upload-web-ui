/**
 * 从任意异常/错误值中提取可读的错误信息文本。
 * 兼容 Error、axios 响应错误(对象带 message)、字符串及原始值。
 */
export function getErrorMessage(e: unknown): string {
  if (e instanceof Error) return e.message
  if (e && typeof e === 'object' && 'message' in e) {
    const m = (e as { message: unknown }).message
    if (typeof m === 'string' && m) return m
  }
  return typeof e === 'string' ? e : String(e)
}
