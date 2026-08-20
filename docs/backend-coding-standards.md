# 后端编码规范 (Backend Coding Standards)

> 适用于 `backend/` 目录（Python）。技术栈：Flask 3.1（async）· Python 3.13 · loguru + 标准 logging（渠道日志）· ruff · pytest。backend-mcp/（TS MCP 服务）见仓库根 `.cursorrules` 前端/通用规则。
> 简明规则见仓库根 `.cursorrules`；本文件为完整版（规则 + 理由 + 坏例/好例 + 治理清单）。

## 0. 技术栈基线

| 项 | 值 |
|---|---|
| Web 框架 | Flask 3.1（`Flask[async]`），蓝图注册于 `blueprints/` |
| 运行时 | Python 3.13（`.venv` 位于 `backend/.venv`） |
| 日志 | 平台实现用 `util/_logger.get_channel_logger("<渠道>")`（按渠道落盘 `logs/{yyyy-MM-dd}/{channel}.log`）；少量模块用 loguru；**禁止 print 调试输出** |
| 浏览器自动化 | cloakbrowser（Playwright 封装），平台实现继承 `impl/base_platform.py:BasePlatform` |
| 存储 | `storage/{local,s3}.py`（本地 + S3，经 `conf.py` 配置） |
| 校验 | ruff（配置见 `backend/pyproject.toml`） |
| 测试 | pytest（当前基线 **408 passed / 3 skipped**） |

**验证命令**（在 `backend/` 下，`.venv` 内）：
```bash
source .venv/bin/activate
ruff check . --exclude .venv
python -m pytest -q
```

---

## 1. 目录结构

| 目录 | 职责 |
|---|---|
| `blueprints/` | Flask 蓝图（每平台一个 `*_bp.py` + 通用 `materials_bp` / `uploads_bp`），只做请求/响应编排 |
| `impl/` | 平台实现（每平台一个目录，`platform.py` 继承 `BasePlatform`；`registry.py` 注册） |
| `services/` | 跨平台服务（发布执行、素材处理、草稿合并、时长修复） |
| `storage/` | 文件存储抽象（base/local/s3） |
| `ext_api/` | 外部 API 客户端 |
| `util/` | 通用工具（日志、视频限制、错误） |
| `routes/` | 非常规路由（如视频帧提取） |

**规则**：新增平台 = `impl/<platform>/` + `blueprints/<platform>_bp.py` + `registry.py` 注册；不把业务逻辑写进蓝图。

---

## 2. 平台实现契约

- 平台类继承 `impl/base_platform.py:BasePlatform`，实现其抽象方法（`login` / `check_cookie` / `publish_video` 等），**不绕过基类**直接操作浏览器。
- 平台内日志：模块级 `logger = get_channel_logger("<channel>")`，渠道名与 `util/_logger.CHANNELS` 对齐。
- 并发发布用 `bind_account_name(name)` 上下文绑定账号昵称，让日志自动归属账号。

---

## 3. 日志

**规则**：
- **禁止 `print()`**（调试残留）。日志一律走渠道 logger 或 loguru。
- 错误路径必须留日志：`logger.warning/error(..., exc_info=True)` 或 `logger.exception(...)`；禁止裸 `except: pass` 吞异常（见规则 4）。
- 日志消息用中文或英文均可，但同一文件内保持一致；结构化字段（账号、渠道）交给 logger 基建注入，不拼进 message。

**坏**：
```python
print(f"[materials] upload error: {e}")
```

**好**：
```python
logger = get_channel_logger("backend")
...
logger.error("上传失败 material_id=%s", material_id, exc_info=True)
```

---

## 4. 异常处理

**规则**：
- **禁止吞异常**：`except: pass` / `except Exception: pass`（ruff S110）、`except: continue`（S112）。若某异常确实可忽略，必须写注释说明原因。
- **禁止裸 except**（BLE001）：`except Exception as e:` 必须带日志；捕获后要么记录、要么抛出、要么明确恢复。
- 不要用 `print` 代替日志记录异常（见规则 3）。

**坏**：
```python
try:
    send_to_api(...)
except Exception:
    pass
```

**好**：
```python
try:
    send_to_api(...)
except ApiTimeoutError as e:
    logger.warning("接口超时, 跳过: %s", e)   # 明确说明为什么可忽略
```

---

## 5. 类型标注

- **新代码 / 改动代码必须带类型标注**（函数参数、返回值、数据结构）。
- 平台实现方法签名与 `BasePlatform` 保持一致（不收敛/放宽参数类型）。
- 存量代码标注覆盖低（139 文件中仅 4 个用 `typing`），按治理批逐步补齐；`type: ignore` 禁止新增。

---

## 6. 时区

- **禁止无时区 `datetime.now()` / `date.today()` / `strptime` 无 zone**（ruff DTZ005/DTZ007/DTZ011）：统一 `datetime.now(tz=ZoneInfo("Asia/Shanghai"))`（业务时区为东八区）。
- 存量 40+ 处违规按治理批修复（见治理清单）。

---

## 7. 导入与格式

- 导入排序交给 ruff isort（I001），提交前 `ruff check --fix`。
- 行宽 ≤ 120；格式遵循 ruff formatter 输出。
- 禁止未使用的导入/变量（F401/F841）；`noqa` 只用于解释性豁免并写原因（RUF100 不允许悬空 noqa）。

---

## 8. 配置

- 配置集中在 `conf.py`；环境变量统一 `SAU_` 前缀（`SAU_DATA_DIR` 等）；不要在各模块散落魔法常量。
- 平台特有可调参数放在平台 impl 内模块常量，命名 `*_LIMIT` / `*_TIMEOUT` 等语义化。

---

## 9. 测试

- pytest；用例放 `backend/tests/` 或源文件旁（`services/test_video.py` 风格）。
- 纯逻辑（解析、校验、合并）必须覆盖；浏览器/外呼类测试用 mock 或跳过（skip 需注明原因）。
- 当前基线 408 passed / 3 skipped；新增代码必须带测试或说明缺测原因。

---

## 10. 治理清单（ruff 基线 2026-08-20）

`ruff check . --exclude .venv` 基线 **1623 个违规**。分批处置（当前已降为 **156**，剩余为风格/低优先项 E402/F841/B904/F541/SIM117/TRY*/SIM105/E501/PLW2901 等，不阻断治理）：

| 批 | 规则 | 数量 | 处置 | 状态 |
|---|---|---|---|---|
| B0 | 规范落盘 + ruff 配置 | — | `pyproject.toml` 基线 + 本文档 | ✅ 2026-08-20 |
| B1 | I001/F401/RUF100 + `print()` | 253 自动 + 15 print | `ruff --fix` + print→logger | ✅ 2026-08-20 |
| B2a | S112 except-continue | 33 | 原因注释 + noqa + 规则解禁 | ✅ 2026-08-20 |
| B2b | S110 try-except-pass | 278 | 原因注释 + noqa + 规则解禁 | ✅ 2026-08-20 |
| B3 | DTZ005/007/011/006 时区 | 49 | 统一 `Asia/Shanghai` 时区 | ✅ 2026-08-20 |
| B4 | BLE001 盲 except | 880 | 原因注释 + noqa + 规则解禁（51 处带 exc_info 日志自动豁免） | ✅ 2026-08-20 |
| B5 | 类型标注试点 | 4/139 文件 | services/draft_merge.py 9 函数 + storage/ 全模块补齐标注 | ✅ 2026-08-20 |
| B6 | G201/PIE810/PLW1510 零散 | 38 | G201 改 exception()、PIE810 合并 tuple、PLW1510 注释 | ✅ 2026-08-20 |

> 规则从 `pyproject.toml` ignore 列表移除 = 该批完成（ruff 重新报错即回归）。

---

*基于 ruff 官方规则集（E/F/I/UP/B/SIM/RUF/TRY/G/DTZ/PLW/BLE/S）与仓库既有模式整理。*
