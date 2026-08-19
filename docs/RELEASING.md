# 发布流程（Release Checklist）

> 目标：让「可发布」有明确定义。合并到 master 前 CI 三个 job 必须全绿（分支保护自动强制），
> 版本信息三处一致，changelog 必须更新。

## 每次发版步骤

| # | 检查项 | 说明 |
|---|--------|------|
| 1 | CI 全绿 | backend-mcp (tsc+vitest) / frontend (vite build) / backend (pytest) —— 分支保护自动强制 |
| 2 | 更新版本号（**三处一致**） | `versions` 文件 · `frontend/package.json` version · `frontend/package-lock.json` version |
| 3 | 新建 changelog | `changelog/YYYYMMDD.html`，复制最新一份改内容（标题含版本号） |
| 4 | 更新 README | README 版本 badge + 版本列表段（vX.Y.Z + 日期 + 要点） |
| 5 | 合并 PR 到 master | 走 PR（禁直推），CI 绿后合并 |
| 6 | 打 tag | `git tag v<版本号>` + `git push origin v<版本号>` |
| 7 | （可选）tag 构建验证 | 手动在 tag 上触发 CI / 构建产物冒烟 |

## 版本号约定

- 版本号唯一来源：`versions` 文件（纯文本，如 `1.2.5`）
- `frontend/package.json` / `package-lock.json` 的 `version` 必须与 `versions` 一致（前端 About 页显示它）
- 新功能 / 修复按语义化版本递增：`major.minor.patch`

## 发版前自查

- [ ] `git status` 干净（无未提交改动）
- [ ] 三处版本号一致
- [ ] changelog 已更新
- [ ] CI 绿（PR 状态）
- [ ] 本地 `pytest` / `vitest` 全绿（CI 之外的最后防线）
