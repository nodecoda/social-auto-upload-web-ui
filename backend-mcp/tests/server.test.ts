import { describe, it, expect } from 'vitest';
import { createMcpServer } from '../src/server';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';

describe('MCP Server', () => {
  it('应该创建MCP服务器实例', () => {
    const server = createMcpServer({
      backendUrl: 'http://localhost:5409',
      dbPath: ':memory:',
    });

    expect(server).toBeDefined();
  });

  it('通过 in-memory 传输注册全部 27 个工具', async () => {
    const server = createMcpServer({
      backendUrl: 'http://localhost:5409',
      dbPath: ':memory:',
    });

    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await server.connect(serverTransport);

    const client = new Client({ name: 'test-client', version: '1.0.0' });
    await client.connect(clientTransport);

    try {
      const res = await client.listTools();
      const names = res.tools.map((t) => t.name).sort();

      expect(names.length).toBe(27);
      // 覆盖 8 个注册模块的关键工具
      for (const expected of [
        'account_list',
        'material_list',
        'draft_list',
        'video_publish',
        'publish_history',
        'settings_get',
        'task_list',
        'queue_status',
        'changelog_list',
      ]) {
        expect(names).toContain(expected);
      }
    } finally {
      await client.close();
      await server.close();
    }
  });
});
