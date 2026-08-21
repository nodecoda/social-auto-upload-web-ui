import { describe, it, expect, vi } from 'vitest';
import { AuthManager } from '../src/auth';
import { BackendClient } from '../src/client';

/** 构造一个 mock BackendClient，get 返回给定 settings。 */
function makeClient(settings: Record<string, unknown>): BackendClient {
  return {
    get: vi.fn().mockResolvedValue({ code: 200, data: settings }),
  } as unknown as BackendClient;
}

describe('auth', () => {
  it('应该从后端 settings 读取 Token', async () => {
    const auth = new AuthManager(makeClient({ mcp_api_token: 'backend-token-456' }));
    await auth.init();

    expect(auth.getToken()).toBe('backend-token-456');
    expect(auth.isAuthEnabled()).toBe(true);
  });

  it('应该验证有效的 Token', async () => {
    const auth = new AuthManager(makeClient({ mcp_api_token: 'valid-token' }));
    await auth.init();

    expect(auth.validateToken('valid-token')).toBe(true);
  });

  it('应该拒绝无效的 Token', async () => {
    const auth = new AuthManager(makeClient({ mcp_api_token: 'valid-token' }));
    await auth.init();

    expect(auth.validateToken('invalid-token')).toBe(false);
  });

  it('未配置 Token 时应该跳过验证', async () => {
    const auth = new AuthManager(makeClient({}));
    await auth.init();

    expect(auth.getToken()).toBe('');
    expect(auth.isAuthEnabled()).toBe(false);
    expect(auth.validateToken('any-token')).toBe(true);
  });

  it('mcp_api_token 为非字符串时应视为未配置', async () => {
    const auth = new AuthManager(makeClient({ mcp_api_token: 12345 }));
    await auth.init();

    expect(auth.getToken()).toBe('');
    expect(auth.isAuthEnabled()).toBe(false);
  });

  it('已启用认证时传入空字符串 Token 应被拒绝', async () => {
    const auth = new AuthManager(makeClient({ mcp_api_token: 'valid-token' }));
    await auth.init();

    expect(auth.validateToken('')).toBe(false);
  });

  it('setTokenForTest 用于测试注入', async () => {
    const auth = new AuthManager(makeClient({}));
    await auth.init();
    auth.setTokenForTest('test-token-123');

    expect(auth.getToken()).toBe('test-token-123');
  });
});
