import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AuthManager } from '../src/auth';

const mocks = vi.hoisted(() => ({ mockInitSqlJs: vi.fn() }));

vi.mock('sql.js', () => ({
  default: mocks.mockInitSqlJs,
}));

describe('auth.init 失败分支', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('sql.js 初始化失败时应捕获异常并记录错误，不向上抛出', async () => {
    mocks.mockInitSqlJs.mockRejectedValue(new Error('wasm load failed'));

    const auth = new AuthManager(':memory:');
    await expect(auth.init()).resolves.toBeUndefined();

    expect(auth.getToken()).toBe('');
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Failed to initialize auth database:',
      expect.any(Error)
    );
  });
});
