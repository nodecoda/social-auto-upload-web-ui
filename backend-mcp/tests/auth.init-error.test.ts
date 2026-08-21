import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AuthManager } from '../src/auth';
import { BackendClient } from '../src/client';

describe('auth.init 失败分支', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('后端不可用时应捕获异常并记录错误，不向上抛出', async () => {
    const client = {
      get: vi.fn().mockRejectedValue(new Error('ECONNREFUSED')),
    } as unknown as BackendClient;

    const auth = new AuthManager(client);
    await expect(auth.init()).resolves.toBeUndefined();

    expect(auth.getToken()).toBe('');
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Failed to load MCP token from backend:',
      expect.any(Error)
    );
  });

  it('后端返回异常结构（无 data）时应视为未配置', async () => {
    const client = {
      get: vi.fn().mockResolvedValue({ code: 500 }),
    } as unknown as BackendClient;

    const auth = new AuthManager(client);
    await auth.init();

    expect(auth.getToken()).toBe('');
    expect(auth.isAuthEnabled()).toBe(false);
  });
});
