# 七、MCP（Model Context Protocol）服务

## 7.1 概述

`backend-mcp/` 是一个 TypeScript 实现的 MCP 服务，为 AI Agent（如 Claude、ZCode 等）提供与千帆云递系统交互的能力。通过 MCP 协议，LLM 可以通过自然语言驱动发布操作。

## 7.2 架构

```
LLM  ←→  MCP 协议 (Stdio / SSE over HTTP)
         ┌──────────────────────────────┐
         │        MCP Server             │
         │  @modelcontextprotocol/sdk    │
         ├──────────────────────────────┤
         │     工具层 (tools/)            │
         │  publish | accounts | drafts  │
         │  materials | tasks | settings │
         │  changelog | publish_extra    │
         ├──────────────────────────────┤
         │      HTTP Client (client.ts)   │
         │  通过 Axios 调用 Flask 后端    │
         ├──────────────────────────────┤
         │     直接 DB 读取 (sql.js)      │
         │  缓存查询，绕过后端 API        │
         └──────────────────────────────┘
                   │
                   ▼
          Flask Backend (:5409)
```

## 7.3 传输模式

| 模式 | 用途 | 说明 |
|------|------|------|
| stdio | Claude Desktop / 本地 CLI | 通过标准输入输出通信 |
| sse | 远程 AI Agent 接入 | HTTP SSE 端点，支持 Token 鉴权 |
| both | 同时启用 | 两个传输通道同时工作 |

## 7.4 工具清单

### 7.4.1 视频发布（publish.ts）

最复杂的工具，提供完整的视频发布参数：

```typescript
server.tool('video_publish', `发布视频到指定平台`, {
    type: z.number().min(1).max(10),       // 平台类型
    title: z.string(),                      // 标题
    material_id: z.string().optional(),     // 视频素材 ID
    account_id: z.union([z.string(), z.number()]).optional(), // 账号 ID
    tags: z.array(z.string()).optional(),   // 标签
    description: z.string().optional(),     // 描述
    thumbnail_material_id: z.string().optional(), // 封面素材
    enableTimer: z.boolean().optional(),    // 是否定时
    scheduleTime: z.string().optional(),    // 定时时间
    aiContent: z.string().optional(),       // AI 声明
    isOriginal: z.boolean().optional(),     // 是否原创
    // ... 各平台特有字段
})
```

### 7.4.2 其他工具

| 工具 | 文件 | 功能 |
|------|------|------|
| accounts | accounts.ts | 列出账号、校验有效性 |
| drafts | drafts.ts | 草稿 CRUD（列表/创建/删除/批量发布） |
| materials | materials.ts | 素材列表、搜索 |
| tasks | tasks.ts | 任务列表、详情 |
| settings | settings.ts | 系统设置（读取/写入） |
| changelog | changelog.ts | 更新日志查询 |
| publish_extra | publish_extra.ts | 扩展发布（图集等） |

## 7.5 鉴权

```typescript
// auth.ts — Token 鉴权
class AuthManager {
    constructor(dbPath: string) {
        // 从 SQLite settings 表读取 MCP_TOKEN
    }
    isAuthEnabled(): boolean { return !!this.token }
    validateToken(token: string): boolean { return token === this.token }
}
```

Token 存储在系统设置中（`settings` 表 `key='MCP_TOKEN'`），通过 SSE 端点的 `Bearer` 或 `?token=` 验证。未配置 Token 时全部放行。

## 7.6 工具生命周期

```typescript
// 每个工具返回标准格式
interface ToolResult {
    content: [{ type: 'text', text: string }];
    isError?: boolean;
}
// 成功: { content: [{ type: 'text', text: JSON.stringify({ code: 200, data }) }] }
// 失败: { content: [{ type: 'text', text: errorMessage }], isError: true }
```
