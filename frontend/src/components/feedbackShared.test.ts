import { describe, it, expect } from 'vitest'
import {
  statusLabel,
  statusTagType,
  truncate,
  maskEmail,
  formatTime,
} from './feedbackShared'

describe('feedbackShared.statusLabel', () => {
  it('映射四种已知状态', () => {
    expect(statusLabel(1)).toBe('待确认')
    expect(statusLabel(2)).toBe('处理中')
    expect(statusLabel(3)).toBe('已完成')
    expect(statusLabel(4)).toBe('已拒绝')
  })

  it('未知状态回退「未知」', () => {
    expect(statusLabel(0)).toBe('未知')
    expect(statusLabel(99)).toBe('未知')
  })
})

describe('feedbackShared.statusTagType', () => {
  it('映射状态到 el-tag type', () => {
    expect(statusTagType(1)).toBe('warning')
    expect(statusTagType(2)).toBe('primary')
    expect(statusTagType(3)).toBe('success')
    expect(statusTagType(4)).toBe('info')
  })

  it('未知状态回退 info', () => {
    expect(statusTagType(0)).toBe('info')
  })
})

describe('feedbackShared.truncate', () => {
  it('短文本原样返回', () => {
    expect(truncate('你好', 80)).toBe('你好')
  })

  it('超长文本截断并追加省略号', () => {
    const text = '一二三四五六七八九十'
    expect(truncate(text, 5)).toBe('一二三四五…')
  })

  it('空文本返回空串', () => {
    expect(truncate('', 5)).toBe('')
  })
})

describe('feedbackShared.maskEmail', () => {
  it('脱敏邮箱:保留前两位与域名', () => {
    expect(maskEmail('abcdef@example.com')).toBe('ab***@example.com')
  })

  it('无 @ 的输入原样返回', () => {
    expect(maskEmail('not-an-email')).toBe('not-an-email')
  })

  it('空输入返回空串', () => {
    expect(maskEmail('')).toBe('')
  })
})

describe('feedbackShared.formatTime', () => {
  it('ISO 时间格式化为可读字符串(含年月日)', () => {
    const out = formatTime('2026-08-20T10:30:00')
    expect(out).toMatch(/2026/)
    expect(out).toMatch(/8\/20|08\/20|8月20/)
  })

  it('空输入返回空串', () => {
    expect(formatTime('')).toBe('')
  })
})
