import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EventEmitter } from 'events';
import fs from 'fs';
import os from 'os';
import path from 'path';
import axios from 'axios';
import FormData from 'form-data';
import { BackendClient } from '../src/client';

vi.mock('axios', () => ({
  default: { create: vi.fn() },
}));

const createMock = vi.mocked(axios.create);

function makeHttpMock() {
  return {
    defaults: { baseURL: 'http://localhost:5409' },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  };
}

function makeStream() {
  const stream = new EventEmitter() as EventEmitter & { destroy: () => void };
  stream.destroy = vi.fn(() => stream.emit('close'));
  return stream;
}

/** 等待 mock http.get 的微任务链完成，确保 stream 监听器已注册 */
function flush() {
  return new Promise<void>((resolve) => setTimeout(resolve, 0));
}

describe('BackendClient', () => {
  const baseUrl = 'http://localhost:5409';
  let http: ReturnType<typeof makeHttpMock>;

  beforeEach(() => {
    http = makeHttpMock();
    createMock.mockReturnValue(http as any);
  });

  it('应该能创建客户端实例', () => {
    const client = new BackendClient(baseUrl);
    expect(client).toBeDefined();
  });

  it('应该正确格式化GET请求路径', () => {
    const client = new BackendClient(baseUrl);
    const url = client.buildUrl('/getAccounts', { id: '123' });
    expect(url).toBe('http://localhost:5409/getAccounts?id=123');
  });

  it('应该正确格式化多个查询参数', () => {
    const client = new BackendClient(baseUrl);
    const url = client.buildUrl('/api/materials/list', {
      type: 'video',
      page: '1',
      page_size: '24'
    });
    expect(url).toBe('http://localhost:5409/api/materials/list?type=video&page=1&page_size=24');
  });

  it('buildUrl 无参数时应返回纯路径', () => {
    const client = new BackendClient(baseUrl);
    expect(client.buildUrl('/plain')).toBe('http://localhost:5409/plain');
  });

  it('get 应携带 params 并返回响应 data', async () => {
    http.get.mockResolvedValue({ data: { code: 0, data: [1, 2, 3] } });
    const client = new BackendClient(baseUrl);

    const res = await client.get('/getAccounts', { type: 'xhs' });

    expect(http.get).toHaveBeenCalledWith('/getAccounts', { params: { type: 'xhs' } });
    expect(res).toEqual({ code: 0, data: [1, 2, 3] });
  });

  it('post 无 timeout 时不应传 config', async () => {
    http.post.mockResolvedValue({ data: { code: 0 } });
    const client = new BackendClient(baseUrl);

    await client.post('/publish', { title: 't' });

    expect(http.post).toHaveBeenCalledWith('/publish', { title: 't' }, undefined);
  });

  it('post 带 timeout 时应透传超时配置', async () => {
    http.post.mockResolvedValue({ data: { code: 0 } });
    const client = new BackendClient(baseUrl);

    await client.post('/login', {}, 5000);

    expect(http.post).toHaveBeenCalledWith('/login', {}, { timeout: 5000 });
  });

  it('put 应携带数据', async () => {
    http.put.mockResolvedValue({ data: { code: 0 } });
    const client = new BackendClient(baseUrl);

    await client.put('/drafts/1', { title: 'new' });

    expect(http.put).toHaveBeenCalledWith('/drafts/1', { title: 'new' });
  });

  it('delete 应调用对应路径', async () => {
    http.delete.mockResolvedValue({ data: { code: 0 } });
    const client = new BackendClient(baseUrl);

    await client.delete('/drafts/1');

    expect(http.delete).toHaveBeenCalledWith('/drafts/1');
  });

  it('uploadFile 应构造 FormData（文件流 + 附加字段）并携带 multipart headers', async () => {
    http.post.mockResolvedValue({ data: { code: 0 } });
    const client = new BackendClient(baseUrl);
    const file = path.join(os.tmpdir(), `upload-${Date.now()}.txt`);
    fs.writeFileSync(file, 'hello');

    try {
      await client.uploadFile('/materials/upload', file, { type: 'video' });

      expect(http.post).toHaveBeenCalledTimes(1);
      const [calledPath, form, config] = http.post.mock.calls[0];
      expect(calledPath).toBe('/materials/upload');
      expect(form).toBeInstanceOf(FormData);
      expect(config.headers).toEqual(form.getHeaders());
      expect(form.getHeaders()['content-type']).toContain('multipart/form-data');
    } finally {
      fs.unlinkSync(file);
    }
  });

  it('getStream 应聚合所有 chunk 直到流结束', async () => {
    const stream = makeStream();
    http.get.mockResolvedValue({ data: stream });
    const client = new BackendClient(baseUrl);

    const promise = client.getStream('/tasks/1/stream', { id: '1' });
    expect(http.get).toHaveBeenCalledWith('/tasks/1/stream', {
      params: { id: '1' },
      responseType: 'stream',
      timeout: 300000,
    });

    await flush();
    stream.emit('data', Buffer.from('part1-'));
    stream.emit('data', Buffer.from('part2'));
    stream.emit('end');

    await expect(promise).resolves.toBe('part1-part2');
  });

  it('getStream 流错误应 reject', async () => {
    const stream = makeStream();
    http.get.mockResolvedValue({ data: stream });
    const client = new BackendClient(baseUrl);

    const promise = client.getStream('/x');
    await flush();
    stream.emit('error', new Error('stream broken'));

    await expect(promise).rejects.toThrow('stream broken');
  });

  it('getSSE 解析 JSON 消息，onMessage 返回终态时 resolve 并断流', async () => {
    const stream = makeStream();
    http.get.mockResolvedValue({ data: stream });
    const client = new BackendClient(baseUrl);

    const promise = client.getSSE('/sse', { taskId: '1' }, (msg) => {
      if (msg && msg.code === 0) return 'DONE';
      return undefined;
    });

    await flush();
    stream.emit('data', Buffer.from('data: {"code":0,"data":{"id":1}}\n\n'));

    await expect(promise).resolves.toBe('DONE');
    expect(stream.destroy).toHaveBeenCalled();
  });

  it('getSSE 多条消息：非 JSON 按原始字符串处理，未返回终态则继续', async () => {
    const stream = makeStream();
    http.get.mockResolvedValue({ data: stream });
    const client = new BackendClient(baseUrl);

    const seen: any[] = [];
    const promise = client.getSSE('/sse', undefined, (msg) => {
      seen.push(msg);
      if (seen.length === 2) return 'FINISHED';
      return undefined;
    });

    await flush();
    stream.emit('data', Buffer.from('data: {"id":1}\n\ndata: hello world\n\n'));

    await expect(promise).resolves.toBe('FINISHED');
    expect(seen).toEqual([{ id: 1 }, 'hello world']);
  });

  it('getSSE 消息跨 chunk 分片时应缓存 buffer 再解析', async () => {
    const stream = makeStream();
    http.get.mockResolvedValue({ data: stream });
    const client = new BackendClient(baseUrl);

    const promise = client.getSSE('/sse', undefined, (msg) => {
      if (msg && msg.id === 2) return 'OK';
      return undefined;
    });

    await flush();
    stream.emit('data', Buffer.from('data: {"id":'));
    stream.emit('data', Buffer.from('2}\n\n'));

    await expect(promise).resolves.toBe('OK');
  });

  it('getSSE onMessage 抛错时应 reject 并断流', async () => {
    const stream = makeStream();
    http.get.mockResolvedValue({ data: stream });
    const client = new BackendClient(baseUrl);

    const promise = client.getSSE('/sse', undefined, () => {
      throw new Error('handler failed');
    });

    await flush();
    stream.emit('data', Buffer.from('data: anything\n\n'));

    await expect(promise).rejects.toThrow('handler failed');
    expect(stream.destroy).toHaveBeenCalled();
  });

  it('getSSE 流自然结束而无终态消息时应 reject', async () => {
    const stream = makeStream();
    http.get.mockResolvedValue({ data: stream });
    const client = new BackendClient(baseUrl);

    const promise = client.getSSE('/sse', undefined, () => undefined);
    await flush();
    stream.emit('end');

    await expect(promise).rejects.toThrow('SSE stream ended without terminal message');
  });

  it('getSSE 流错误应 reject', async () => {
    const stream = makeStream();
    http.get.mockResolvedValue({ data: stream });
    const client = new BackendClient(baseUrl);

    const promise = client.getSSE('/sse', undefined, () => undefined);
    await flush();
    stream.emit('error', new Error('net down'));

    await expect(promise).rejects.toThrow('net down');
  });
});
