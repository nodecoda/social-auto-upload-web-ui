import { describe, it, expect, vi, beforeEach } from 'vitest';
import fs from 'fs';
import os from 'os';
import path from 'path';
import initSqlJs from 'sql.js';
import { AuthManager } from '../src/auth';

describe('auth', () => {
  const mockDbPath = ':memory:';

  it('应该从数据库读取Token', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();
    // 模拟数据库中有token
    auth.setTokenForTest('test-token-123');

    expect(auth.getToken()).toBe('test-token-123');
  });

  it('应该验证有效的Token', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();
    auth.setTokenForTest('valid-token');

    expect(auth.validateToken('valid-token')).toBe(true);
  });

  it('应该拒绝无效的Token', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();
    auth.setTokenForTest('valid-token');

    expect(auth.validateToken('invalid-token')).toBe(false);
  });

  it('未配置Token时应该跳过验证', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();
    auth.setTokenForTest('');

    expect(auth.validateToken('any-token')).toBe(true);
    expect(auth.isAuthEnabled()).toBe(false);
  });

  it('应从文件数据库的 settings 表加载 Token（真实 SELECT 路径）', async () => {
    const file = path.join(os.tmpdir(), `auth-test-${Date.now()}.db`);
    try {
      const SQL = await initSqlJs();
      const db = new SQL.Database();
      db.run('CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)');
      db.run("INSERT INTO settings VALUES ('mcp_api_token', 'file-token-456')");
      fs.writeFileSync(file, Buffer.from(db.export()));

      const auth = new AuthManager(file);
      await auth.init();

      expect(auth.getToken()).toBe('file-token-456');
      expect(auth.isAuthEnabled()).toBe(true);
    } finally {
      fs.unlinkSync(file);
    }
  });

  it('数据库文件不存在时应创建空库且不启用认证（loadToken 容错记录错误）', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const file = path.join(os.tmpdir(), `auth-missing-${Date.now()}.db`);
      const auth = new AuthManager(file);
      await auth.init();

      expect(auth.getToken()).toBe('');
      expect(auth.isAuthEnabled()).toBe(false);
      // 文件分支未建 settings 表，loadToken 捕获并记录 'no such table'
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Failed to load MCP token:',
        expect.any(Error)
      );
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it('内存库 settings 表为空时 Token 保持为空', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();

    expect(auth.getToken()).toBe('');
  });

  it('已启用认证时传入空字符串 Token 应被拒绝', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();
    auth.setTokenForTest('valid-token');

    expect(auth.validateToken('')).toBe(false);
  });
});
