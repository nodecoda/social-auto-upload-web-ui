import { describe, it, expect } from 'vitest'
import {
  statusLabel,
  formatTime,
  formatDuration,
} from './publishHistoryShared'

describe('publishHistoryShared.statusLabel', () => {
  it('映射六种已知状态', () => {
    expect(statusLabel('pending')).toBe('等待中')
    expect(statusLabel('running')).toBe('发布中')
    expect(statusLabel('success')).toBe('全部成功')
    expect(statusLabel('partial')).toBe('部分失败')
    expect(statusLabel('failed')).toBe('全部失败')
    expect(statusLabel('cancelled')).toBe('已取消')
  })

  it('未知状态原样返回', () => {
    expect(statusLabel('weird')).toBe('weird')
  })
})

describe('publishHistoryShared.formatTime', () => {
  it('ISO 时间格式化为月日时分', () => {
    const out = formatTime('2026-08-20T09:05:00')
    expect(out).toMatch(/8\/20|08\/20|8月20/)
    expect(out).toMatch(/9:05|09:05/)
  })

  it('空值返回空串', () => {
    expect(formatTime(undefined)).toBe('')
    expect(formatTime('')).toBe('')
  })
})

describe('publishHistoryShared.formatDuration', () => {
  it('小于 60 秒返回秒', () => {
    expect(formatDuration(5)).toBe('5秒')
    expect(formatDuration(0)).toBe('0秒')
  })

  it('大于等于 60 秒返回分秒', () => {
    expect(formatDuration(60)).toBe('1分0秒')
    expect(formatDuration(125)).toBe('2分5秒')
  })

  it('空值返回空串', () => {
    expect(formatDuration(null)).toBe('')
    expect(formatDuration(undefined)).toBe('')
  })
})
