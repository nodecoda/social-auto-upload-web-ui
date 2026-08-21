# AGENTS.md — social-auto-upload-web-ui

仓库定位：社交平台自动上传 Web UI（前端 Vue3+TS + 后端 Python Flask + backend-mcp TS）。
本文件是 Codex/Claude 等 agent 在本仓库工作的操作契约。详细编码规范见
`docs/frontend-coding-standards.md` 与 `docs/backend-coding-standards.md`。

---

## 1. 包安装源（强制规则，2026-08-21 固化）

本机位于国内网络环境，**所有包管理器一律走国内镜像源**，禁止直连官方源（极慢/超时）。

| 工具 | 配置值 | 说明 |
| --- | --- | --- |
| pip | `~/.pip/pip.conf` → `index-url = https://pypi.tuna.tsinghua.edu.cn/simple` | 清华 PyPI，全局生效 |
| uv | `UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple` | 生成 `requirements.lock` 时用（见 `backend/scripts/refresh-deps-lock.sh`） |
| npm | `~/.npmrc` → `registry=https://registry.npmmirror.com` | 全局 npmmirror |
| playwright 二进制 | `~/.npmrc` → `playwright_download_host=https://cdn.npmmirror.com/binaries/playwright` | 加速浏览器下载 |

**例外（必须切官方源 + 代理，用完即切回）：**
- `npm audit`：npmmirror 不支持 advisory 接口（返回 404）。审计时显式
  `npm audit --registry=https://registry.npmjs.org`，并先 `export http_proxy="http://127.0.0.1:10809" https_proxy="http://127.0.0.1:10809"`。
- `pip-audit`：走清华源也能跑，但更新漏洞库需代理（`--proxy` 或环境变量）。
- 其他需要官方元数据的操作同理。

**规则：**
- 安装/升级 Python 包后必须用 `uv pip compile` 重新生成 `requirements.lock`（国内源），并跑 `pip-audit -r requirements.lock --no-deps` 确认 0 已知漏洞。
- 升级 npm 依赖后跑 `npm audit --registry=https://registry.npmjs.org`（带代理）确认 0 漏洞。
- 不许把 `registry.npmjs.org` / `pypi.org` 直连写进仓库级 `.npmrc`/`pip.conf`（会让 CI 或他人变慢）；镜像源只放用户级配置或环境变量。

---

## 2. 工作节奏（约定）

- **每批一 PR**：一个主题一个分支一个 PR，全量验证绿后 `gh pr merge --merge --delete-branch` 自动合并，然后 `git checkout master && git pull --ff-only`。
- **自动 commit**：达到验证通过即可提交，不等待确认；提交信息中文、写明动机。
- **验证基线**：
  - 后端：`cd backend && ./.venv/bin/python -m pytest -q --no-header -p no:cacheprovider`（当前 3391 passed + 12 skipped）+ `ruff check .` 0 错 + `pip-audit -r requirements.lock --no-deps` 0 漏洞。
  - 前端：`cd frontend && npm test`（vitest）+ `npm run test:coverage`（门槛 90%）+ `npm run build` + `npm audit --audit-level=high --registry=https://registry.npmjs.org`（带代理）0 漏洞。
  - CI：4 checks（backend / backend-mcp / frontend / frontend-visual）全绿才合并。
- 汇报用中文，简洁：目标 → 动作 → 证据/阻塞。
