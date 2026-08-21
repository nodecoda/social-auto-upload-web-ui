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

**新增平台 Checklist（对齐架构整改 R1/R2/R8 后契约，`test_platform_contracts.py` 全量断言）**：

- [ ] 平台类继承 `BasePlatform`，注册到 `impl/registry.py`（`platform_id` / `platform_key` / `platform_name` 齐备且唯一）
- [ ] 发布契约形态：`publish_video` 与基类签名一致；**禁止**「`asyncio.run` 桥接后无条件 `return True`」吞异常（异常须捕获记录并返回 `False`）
- [ ] 浏览器生命周期：创建走 `self.create_browser`，**禁止直接 `browser.close()`**——收尾一律 `await self.close_browser(browser)`（线程内 sync 场景用 `asyncio.run(close_browser(browser))`）
- [ ] **禁止 `asyncio.get_event_loop()`**（3.12 弃用）；轮询计时用 `asyncio.get_running_loop().time()`；Flask 线程跑协程用 `util.async_utils.run_async`
- [ ] cookie 域声明：`platform_cookie_domain` 或 `_parse_cookie_to_storage_state` 按基类模板实现，不逐字节复制
- [ ] 元数据单源：平台名/键以类属性为准，`conf.PLATFORM_MAP` / blueprint 映射改为派生，不另立常量表
- [ ] 必要测试：`tests/test_<platform>_platform_dom.py`（DOM 交互契约）+ 注册表可达性断言；CI 4 道检查全绿后合并

> 对照红线见 `backend/tests/test_platform_contracts.py`（注册表结构 / `browser.close` 直调 / `get_event_loop` / 吞失败反模式，违规即 CI 失败）。

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

> **2026-08-21 更新：ruff 已入 CI 强制门槛**（PR #153，`ruff check .` 0 错才合并）。当前 **All checks passed = 0 违规**。
> **2026-08-21 更新：mypy 已入 CI 强制门槛**（PR #156，核心域 services/ext_api 0 错）。覆盖率门槛已抬升（PR #155：后端 34→80%，前端 80→85%）。
> 依赖漏洞也已入 CI：后端 `pip-audit -r requirements.lock --no-deps`、前端 `npm audit --audit-level=high` 0 漏洞。

`ruff check . --exclude .venv` 基线 **1623 个违规**。分批处置（当前已降为 **0**，All checks passed）：

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
| C1 | F841 未使用变量 | 19 | 逐处审查删除（含 jd 同模式误删修复） | ✅ 2026-08-21 |
| C2 | B904 异常链 | 13 | 包装型 `from e` / 裸捕获 `from None`；顺带移除 9 处冗余 BLE001 noqa | ✅ 2026-08-21 |
| C3 | PLW0603 global | 8 | 惰性单例/缓存逐组审查确认竞态安全 + noqa 注释 | ✅ 2026-08-21 |
| C4 | F541/F401 | 17 | f-string 无占位符 safe-fix + 未用导入删除 | ✅ 2026-08-21 |
| D1 | E701 单行多语句 | 10 | cookie 解析/空行守卫拆行（9 平台同模式） | ✅ 2026-08-21 |
| D2 | UP031 % 格式化 | 8 | 列表推导 `%d` → f-string | ✅ 2026-08-21 |
| D3 | SIM115 裸 open | 6 | `NamedTemporaryFile`/open 改 with 上下文 | ✅ 2026-08-21 |
| D4 | SIM117 嵌套 with | 10 | 合并单 with 多上下文（feedback/templates 测试） | ✅ 2026-08-21 |
| D5 | RUF012 可变类属性 | 4 | `ClassVar` 注解（csdn cookie 映射/alipay 声明映射） | ✅ 2026-08-21 |
| D6 | RUF006 asyncio 弱引用 | 3 | 官方 set 持有模式（_browser watchdog/jd/taobao 关闭任务） | ✅ 2026-08-21 |
| D7 | G003/B023/SIM102/B007 零散 | 6 | 日志拼接改 %s、循环变量绑定、合并 if、未用变量下划线 | ✅ 2026-08-21 |
| D8 | RUF100 冗余 noqa | 24 | per-file-ignores 覆盖后自动清理（app.py E402 等） | ✅ 2026-08-21 |

> 规则从 `pyproject.toml` ignore 列表移除 = 该批完成（ruff 重新报错即回归）。

---

*基于 ruff 官方规则集（E/F/I/UP/B/SIM/RUF/TRY/G/DTZ/PLW/BLE/S）与仓库既有模式整理。*
