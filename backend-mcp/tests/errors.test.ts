import { describe, it, expect } from 'vitest';
import { translateError, formatErrorResult, ErrorCodes, type McpError } from '../src/errors';

describe('translateError', () => {
  it('Flask 400 + "缺少必填字段" → MISSING_REQUIRED_FIELD', () => {
    const e = translateError({ code: 400, msg: '缺少必填字段: type', data: null });
    expect(e.code).toBe(4001);
    expect(e.error).toBe('MISSING_REQUIRED_FIELD');
    expect(e.retryable).toBe(false);
  });

  it('Flask 401 + Cookie 失效 → AUTH_FAILED + retryable', () => {
    const e = translateError({ code: 401, msg: 'Cookie 已失效', data: null });
    expect(e.code).toBe(4011);
    expect(e.error).toBe('AUTH_FAILED');
    expect(e.retryable).toBe(true);
  });

  it('Flask 404 → ENDPOINT_NOT_FOUND', () => {
    const e = translateError({ code: 404, msg: '素材不存在', data: null });
    expect(e.code).toBe(4003);
    expect(e.error).toBe('MATERIAL_NOT_FOUND');
  });

  it('Flask 500 → INTERNAL_ERROR', () => {
    const e = translateError({ code: 500, msg: '数据库连接失败', data: null });
    expect(e.code).toBe(5001);
    expect(e.error).toBe('INTERNAL_ERROR');
    expect(e.retryable).toBe(false);
  });

  it('网络错误（无响应）→ NETWORK_ERROR', () => {
    const e = translateError(null, new Error('ECONNREFUSED'));
    expect(e.code).toBe(6001);
    expect(e.error).toBe('NETWORK_ERROR');
    expect(e.retryable).toBe(true);
  });

  it('未知错误码 → INTERNAL_ERROR', () => {
    const e = translateError({ code: 418, msg: '我是茶壶', data: null });
    expect(e.code).toBe(5001);
  });

  it('Flask 400 + "未登录" → AUTH_FAILED + retryable', () => {
    const e = translateError({ code: 400, msg: '请先登录后再操作', data: null });
    expect(e.code).toBe(4011);
    expect(e.error).toBe('AUTH_FAILED');
    expect(e.retryable).toBe(true);
  });

  it('Flask 404 + "账号不存在" → ACCOUNT_NOT_FOUND', () => {
    const e = translateError({ code: 404, msg: '账号不存在', data: null });
    expect(e.code).toBe(4004);
    expect(e.error).toBe('ACCOUNT_NOT_FOUND');
    expect(e.suggestion).toContain('account_list');
  });

  it('Flask 404 + "草稿不存在" → DRAFT_NOT_FOUND', () => {
    const e = translateError({ code: 404, msg: '草稿不存在', data: null });
    expect(e.code).toBe(4005);
    expect(e.error).toBe('DRAFT_NOT_FOUND');
  });

  it('Flask 404 + "任务不存在" → TASK_NOT_FOUND', () => {
    const e = translateError({ code: 404, msg: '任务不存在', data: null });
    expect(e.code).toBe(4006);
    expect(e.error).toBe('TASK_NOT_FOUND');
  });

  it('Flask 400 + "不能为空" → MISSING_REQUIRED_FIELD', () => {
    const e = translateError({ code: 400, msg: '标题不能为空', data: null });
    expect(e.code).toBe(4001);
    expect(e.error).toBe('MISSING_REQUIRED_FIELD');
  });

  it('Flask 404 + 无匹配关键词 → INTERNAL_ERROR', () => {
    const e = translateError({ code: 404, msg: '服务器开了个小差', data: null });
    expect(e.code).toBe(5001);
    expect(e.error).toBe('INTERNAL_ERROR');
  });

  it('flaskResp 为 null 且无网络错误 → NETWORK_ERROR + 默认提示', () => {
    const e = translateError(null);
    expect(e.code).toBe(6001);
    expect(e.error).toBe('NETWORK_ERROR');
    expect(e.message).toBe('无法连接后端');
    expect(e.retryable).toBe(true);
  });

  it('网络错误应保留原始 message', () => {
    const e = translateError(null, new Error('timeout of 300000ms exceeded'));
    expect(e.message).toBe('timeout of 300000ms exceeded');
  });

  it('flaskResp 缺少 msg 时应回退为 "未知错误"', () => {
    const e = translateError({ code: 500 } as any);
    expect(e.message).toBe('未知错误');
  });
});

describe('formatErrorResult', () => {
  it('应返回 isError 的文本工具结果，内容为可解析的 McpError JSON', () => {
    const err: McpError = {
      code: 4011,
      error: 'AUTH_FAILED',
      message: 'Cookie 已失效',
      suggestion: '调 account_login 重新登录该平台账号',
      retryable: true,
      details: { platform: 'douyin' },
    };

    const result = formatErrorResult(err);

    expect(result.isError).toBe(true);
    expect(result.content[0].type).toBe('text');
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.code).toBe(4011);
    expect(parsed.error).toBe('AUTH_FAILED');
    expect(parsed.retryable).toBe(true);
    expect(parsed.details).toEqual({ platform: 'douyin' });
  });
});
