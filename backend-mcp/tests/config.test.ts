import { describe, it, expect, beforeEach } from 'vitest';
import { loadConfig } from '../src/config';

describe('config', () => {
  beforeEach(() => {
    delete process.env.BACKEND_URL;
    delete process.env.MCP_PORT;
    delete process.env.TRANSPORT_MODE;
    delete process.env.DB_PATH;
  });

  it('应该返回默认配置', () => {
    const config = loadConfig();
    expect(config.backendUrl).toBe('http://localhost:5409');
    expect(config.mcpPort).toBe(5410);
    expect(config.transportMode).toBe('both');
  });

  it('应该支持环境变量覆盖', () => {
    process.env.BACKEND_URL = 'http://localhost:8080';
    process.env.MCP_PORT = '3000';

    const config = loadConfig();
    expect(config.backendUrl).toBe('http://localhost:8080');
    expect(config.mcpPort).toBe(3000);
  });

  it('DB_PATH 环境变量应覆盖默认数据库路径', () => {
    process.env.DB_PATH = '/custom/path/custom.db';

    const config = loadConfig();
    expect(config.dbPath).toBe('/custom/path/custom.db');
  });

  it('TRANSPORT_MODE 应支持 stdio 与 sse', () => {
    process.env.TRANSPORT_MODE = 'stdio';
    expect(loadConfig().transportMode).toBe('stdio');

    process.env.TRANSPORT_MODE = 'sse';
    expect(loadConfig().transportMode).toBe('sse');
  });

  it('TRANSPORT_MODE 非法值应按类型透传', () => {
    process.env.TRANSPORT_MODE = 'websocket';
    expect(loadConfig().transportMode).toBe('websocket');
  });

  it('MCP_PORT 非数字时应返回 NaN', () => {
    process.env.MCP_PORT = 'abc';
    expect(Number.isNaN(loadConfig().mcpPort)).toBe(true);
  });

  it('默认 dbPath 应为绝对路径且指向 data/db/database.db', () => {
    const config = loadConfig();
    expect(config.dbPath).toContain('data/db/database.db');
    expect(config.dbPath.startsWith('/')).toBe(true);
  });
});
