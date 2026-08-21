import { BackendClient } from './client.js';

/**
 * MCP 鉴权管理：从后端 `/api/v2/settings` 读取 `mcp_api_token`。
 *
 * 历史：曾用 sql.js 直读 SQLite（settings 表），与后端并发写存在快照读取
 * 风险且耦合 DB schema。现收敛为单一数据通道（HTTP API），token 的唯一
 * 真相源在后端 settings 表（/api/v2/settings 本就全量返回）。
 */
export class AuthManager {
  private token: string = '';

  constructor(private client: BackendClient) {}

  async init(): Promise<void> {
    try {
      const res = await this.client.get<Record<string, unknown>>('/api/v2/settings');
      const data = res?.data ?? {};
      const token = data['mcp_api_token'];
      this.token = typeof token === 'string' ? token : '';
    } catch (error) {
      console.error('Failed to load MCP token from backend:', error);
    }
  }

  getToken(): string {
    return this.token;
  }

  isAuthEnabled(): boolean {
    return this.token.length > 0;
  }

  validateToken(providedToken: string): boolean {
    if (!this.isAuthEnabled()) {
      return true;
    }
    return this.token === providedToken;
  }

  // 用于测试
  setTokenForTest(token: string): void {
    this.token = token;
  }
}
