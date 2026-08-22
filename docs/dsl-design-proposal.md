# 发布操作 DSL 设计提案（2026-08-22 · v0.3）

> 状态：**草案待评审**（决策点见 §14）
> 背景：多平台架构 review（`docs/multiplatform-architecture-review-20260822.md`）识别出大量跨平台重复原语与行为层契约分叉。
> 参考实现：`/home/dev/ph-dsl`（ParseHub DSL——已实现的文本 DSL + 编译器，本提案 v0.2 将其吸收为架构参考，见 §7）。
> 定位：把「发布/登录操作配置化、脚本化」的诉求，落成一份可评审的设计提案。本文只做设计，不构成实施承诺。
> v0.3 变更（2026-08-22）：新增 §11「AI 作者面协议」——AI 一次性编写/修复 DSL、编译器门禁裁决、运行时零 LLM 确定性执行的作者面契约；同步修订 §2 非目标（漂移处置边界）、§6（AI 可写性判据）、§10（静态校验项）；原 §11-§14 顺延为 §12-§15。

---

## 1. 背景与动机（证据驱动）

上一轮 review 的核心发现：**同一契约被重复实现且实现各不相同**。

| 原语 | 重复现状 | 证据 |
|---|---|---|
| cookie 解析 `_parse_cookie_to_storage_state` | 16 个平台逐字节相同实现 | `xiaohongshu/platform.py:76-90` ≡ `weibo/platform.py:54-68` |
| 定时设置 `_set_schedule_time` | 13 平台同名同签名 + 3 个变体名 | `xiaohongshu:1348`、`channels:1062`、`douyin:794` 等 |
| 封面处理 `_set_thumbnail`/`_upload_cover` | 9-10 处 | `xiaohongshu:1086`、`channels:852`、`tencent_video:655` 等 |
| 账号 cookie 路径 `_get_account_cookie_file` | 10 个 blueprint 复制 | alipay/bilibili/channels/douyin_image/kuaishou_image 等 |
| 清空输入 `clear_and_type` | 13 平台复用 + youtube 另写一套 | `_utils.py:1456` vs `youtube/platform.py:564` |

**根因判断**：契约（`BasePlatform` 抽象方法）粒度停在方法级（`publish_video(**kwargs) -> bool`），每个平台必须自己把内部 30+ 步骤重新写一遍。DSL 的本质是**把契约粒度从方法级下沉到动作级，把实现从代码变成数据**。

**核心价值**：分离 *intent*（发布意图，平台无关）与 *encoding*（DOM 交互步骤，平台相关）。网站改版 = 目标 ISA 变化 → 只动该平台的 encoding 声明，意图与编排零改动（**变化局部化**）。

---

## 2. 目标与非目标

### 目标
- 发布/登录流程**声明化**：平台目录从 200-2000 行代码 → 声明式流程 + 少量 hook
- 跨平台重复原语收敛为**单一运行时**（builtin）
- 新平台接入成本从「复制粘贴 + 调参」降为「写一份声明」
- 用 DSL 声明**自动生成契约测试**（对标现有 20 个 `*_platform_dom.py`）
- 特判数据化：`if platform == 'douyin'` 类分支 → capability 声明
- **复用已验证的编译器架构**（参考 ph-dsl，§7），不重写编译器轮子

### 非目标
- ❌ 不发明一门新文本语言 + 从零写编译器（有现成参考：ph-dsl 的管线已验证）
- ❌ 不在运行时解决 DOM 选择器漂移（网站侧本质约束）——漂移处置走离线 AI 修复回路（§11.4），运行时保持确定性、零 LLM 调用；风控/验证码类转人工兜底
- ❌ 不替代发布队列架构（S2 队列合并与本提案正交，**必须先行**）

---

## 3. 核心模型：三层契约

| 层 | 类比 | 内容 | 归属 |
|---|---|---|---|
| **意图契约**（what） | 高级语言源码 | 发布参数模型：标题/标签/封面/定时/可见性/合集，平台无关 | 1 份 |
| **编码契约**（how） | 目标 ISA | 每平台 DOM 交互步骤（DSL 实例） | 每平台 1 份 |
| **编排契约**（state） | 运行时 | 状态机、重试、取消、历史落库 | 1 份 |

分层原则：
- 意图契约 = 现有 `platforms.ts` settingsFields + 后端发布参数的**统一数据模型**（当前缺后端侧统一模型，散落在各 `**kwargs` 与 draft_merge）
- 编码契约 = 本 DSL 的主体
- 编排契约 = 现有 `publish_history.py`/task_queue 收敛后的唯一状态机（S3）

**语言级契约的形式参照**：ph-dsl 用 `template ... receive_data { 字段签名 }` + `run { goto_template ... pass_data {...} }` 在**编译期强制**契约（目标存在、字段名匹配、必填字段齐全、类型可赋值，见 §7.2）。发布 DSL 的意图契约应采用同样的编译期强校验，而不是运行期散落判断。

---

## 4. 原语清单（builtin runtime，第一版）

从现有重复实现中提炼的第一批原语（全部有代码证据支撑）：

| 原语 | 职责 | 参数化点 | 现状证据 |
|---|---|---|---|
| `parse_cookie` | cookie 字符串 → storage_state | 域名列表（平台声明） | 16 平台重复 |
| `set_schedule_time` | 日历/输入框定时 | 选择器策略、日期格式 | 13+3 重复 |
| `set_thumbnail` / `upload_cover` | 封面上传 | 文件 input 选择器、点击顺序 | 9-10 处 |
| `clear_and_type` | 清空+输入 | 清空策略（Ctrl+A/逐键） | 13 复用 + 1 偏离 |
| `upload_file` | 视频/图片上传 | input 选择器、等待策略 | 各平台重复 |
| `get_account_cookie_file` | 账号 cookie 路径解析 | 无（纯通用） | 10 个 bp 复制 |
| `wait_for_selector` | 显式等待 | timeout、状态判定 | 各平台重复 |
| `click_by_text` | 文本定位点击 | 精确/模糊、空格归一 | alipay「完 成」特判 |
| `confirm_publish` | 发布按钮确认 | 按钮文案、成功判定 | 各平台重复 |

**归属规则**：原语 = 跨 ≥2 平台复用的交互动作，收进共享运行时；仅单平台使用的逻辑（如各 `scrape_*_profile`）**留在平台目录**，不进原语库（对齐 review 建议 S7）。

---

## 5. 能力模型（capability matrix）

用数据替换散落的 `if platform ==` 特判（现状证据：`draft_merge.py:218,231`、`task_queue.py:261-298`、`image_publish_bp.py:171-183`）：

```python
@dataclass(frozen=True)
class PlatformCapability:
    video: bool
    image: bool            # 图集
    note: bool             # 图文笔记（小红书形态）
    schedule: bool         # 定时发布
    cover: bool            # 自定义封面
    collections: bool      # 合集
    music: bool            # 音乐/位置搜索等辅助
    cookie_import: bool
    min_video_seconds: float = 0.0
    max_video_seconds: float | None = None
    max_video_bytes: int | None = None
```

- 能力声明与 DSL 流程文件同目录（`impl/<platform>/flow.ph`），注册进 registry
- 前端 `platforms.ts` 的 `settingsFields` 与后端 capability 通过共享契约对齐（review 建议 S4 的落地载体）
- **能力模型是 DSL 的类型系统**：静态校验「该平台声明了 `schedule: False` 就不允许流程里出现 `SetSchedule` 步骤」——参考 ph-dsl 命令 schema 的"只接受这些 option"编译期强制（§7.2）

---

## 6. DSL 语法草案（声明式 EDSL，数据驱动）

形态：**Python 数据结构的声明式流程**（不是新文本语言），运行时逐条解释执行：

```python
# impl/douyin/flow.py
DOUYIN_FLOW = PublishFlow(
    capability=PlatformCapability(
        video=True, image=False, schedule=True, cover=True,
        max_video_seconds=960,
    ),
    publish=Steps([
        Open("https://creator.douyin.com/creator-micro/content/upload"),
        UploadFile(source="video", selector="input[type=file]"),
        Fill("title", source="draft.title", selector="#post-title"),
        FillTags(source="draft.tags", strategy=TAG_INPUT_EACH),
        SetCover(source="draft.cover", fallback="ffmpeg_thumb"),
        SetSchedule(source="draft.publish_date", mode=ScheduleMode.CALENDAR),
        Publish(confirm="发布", success=wait_for("div:has-text('发布成功')")),
    ]),
    hooks={
        # 逃逸口：声明式无法表达的步骤
        "before_publish": "douyin._pre_publish_patch",
    },
)
```

设计要点：
- **Step = (动作原语, 参数, 数据源绑定)**；数据源绑定统一指向 draft/账号上下文，杜绝各平台自行 `**kwargs` 解包
- 执行器是唯一解释器：`run_flow(flow, ctx)` → 逐步调用 builtin，统一日志/重试/超时
- 平台类退化为薄壳：`publish_video` → `run_flow(DOUYIN_FLOW, ctx)`（保持 `BasePlatform` 对外契约不变）

**原判断（v0.1）**：EDSL 而非文本 DSL——理由为免写解析器、hook 即 Python 函数、可复用 mypy。

**v0.2 修正（引入 ph-dsl 证据后）**：文本 DSL 的"解析器成本"已被 ph-dsl 证伪——管线是现成的，`check/fmt/verified IR` 都是已验证组件。**EDSL 仍是可选项，但不再是唯一推荐**；文本 DSL 在 ph-dsl 骨架复用前提下成本骤降，且获得 EDSL 没有的编译期契约强校验与 IR 产物（详见 §7 与 §14 决策点 1）。

**v0.3 补充（AI 可写性判据）**：语言形态决策首次纳入「AI 作者面」视角（§11）——AI 负责一次性生成/修复声明，编译器门禁负责裁决。文本 DSL（.ph）因「源码即 diff、语法形式化、`check` 门禁现成」对 AI 生成成功率与可审计性更优，进一步支撑决策点 1 的选项 B（详见 §14 决策点 1）。

---

## 7. 参考实现：/home/dev/ph-dsl（已存在的同类 DSL）

### 7.1 定位与形态
ParseHub DSL：**文本语言（`.ph`）+ 编译器 + Playwright 运行时**的浏览器提取程序 DSL。编译管线：`解析 → 名字解析 → 类型检查 → verified IR（零诊断才产出）→ 运行时`；CLI 提供 `parsehub run/check/fmt`。已通过 git 历史收敛为单一权威架构（`AGENTS.md` + 全量测试）。

### 7.2 可迁移的设计（按价值排序）

| # | ph-dsl 组件 | 证据 | 迁移到发布 DSL 的收益 |
|---|---|---|---|
| 1 | **Profile/Session 模型**：`parsehub session login`（有头人工登录捕获）→ `storage_state.json`；`session verify`（有界浏览器探针 → active/stale/revoked/unknown）；`session export` | `docs/PROFILES_SESSIONS_ENVIRONMENTS.md`；`src/parsehub/login_capture.py` | **直接替代** social-auto-upload 的 cookie 三件套：16× `_parse_cookie_to_storage_state` + `check_cookie` + `sync_profile` 消亡，统一为"会话"模型 |
| 2 | **语言级契约**：`template receive_data {签名}` / `goto_template pass_data`，编译期强制字段匹配/类型/必填 | `docs/DSL_SYNTAX_REFERENCE.md §12` | 意图契约以编译期强校验落地（§3），杜绝运行期散落判断 |
| 3 | **verified IR 门禁**：有诊断即不产出 IR（`require_verified_ir()`） | `src/parsehub/compiler.py`；`compile.py` 四步管线 | 发布流程声明同样"编译不过不发"，质量问题前置 |
| 4 | **check/fmt 静态工具**：不跑浏览器即完成静态校验与格式化 | README `parsehub check/fmt` | §10 静态校验直接复用，零成本 |
| 5 | **命令 schema 权威表**：每个命令只接受精确 option 集，编译期拒绝未知项 | `src/parsehub/command_schema.py`（CommandSchema/CommandOptionSpec/CommandAuthorityException）；`DSL_SYNTAX_REFERENCE.md §10` | 能力模型的类型系统骨架（§5） |
| 6 | **IR → 自然语言指令生成**（InstructionGenerator） | `compile.py` Step 4 | 从平台发布 DSL 自动生成"平台操作说明"与 golden 契约测试骨架（§9 增强） |
| 7 | **typed parameters + 约束**（min/max/default/description） | `examples/search_interaction_scroll.ph` | 发布参数模型（标题/标签/封面）带编译期约束 |
| 8 | **显式 Boundaries 文档纪律**（非目标明确列出） | `docs/CAPABILITIES.md` Boundaries 节 | §2 非目标已有，保持同样纪律 |

### 7.3 差距分析（ph-dsl → 发布 DSL 缺什么）

| 差距 | 说明 | 应对 |
|---|---|---|
| **命令语义域不同** | ph-dsl 是提取域（select/begin_entry/extract/collect_data 所有权模型）；发布域需要 upload/schedule/cover/confirm | 不硬塞进 ph-dsl 的提取所有权模型（会双败），见 7.4 |
| **无文件上传/定时/封面/发布确认命令** | 交互命令仅 click/input/hover/scroll/wait（`DSL_SYNTAX_REFERENCE §10`） | 发布命令集需新定义（§4 原语 → 命令） |
| **无逃逸口** | ph-dsl 是封闭世界（"Only these options are accepted"）；发布域必须开放 hook | §8 逃逸口设计是发布 DSL 的**新增面** |
| **无多账号×多草稿编排** | ph-dsl 单 run 单 profile；发布需与队列（S2 合并后的唯一内核）集成 | 编排层在 DSL 之外（services），DSL 只描述单平台单次发布 |
| **无反检测/humanize** | social-auto-upload 已有 CloakBrowser humanize 层 | 作为运行时上下文注入（`humanize=True` 属执行参数非语言语义） |

### 7.4 复用路径（两条，供决策点 1 选）

- **路径 A：库复用（耦合）**——把 ph-dsl 作为依赖引入，在其上扩展 publish 命令。风险：提取语义与发布语义共存一个 IR/所有权模型，双方都会变味；ph-dsl 是独立产品（自带 CLI/profile store），引入会拉进大量无关能力。
- **路径 B：同构兄弟（推荐）**——抽取 ph-dsl 已验证的**骨架**为共享核心：编译管线（parse→resolve→typecheck→verified IR）、session/profile store、check/fmt 工具、命令 schema 权威表模式。发布 DSL 用同一骨架 + **自己的命令集与 IR 语义**（publish 域）+ Playwright 运行时（可复用 social-auto-upload 现有 CloakBrowser 层）。
  - 类比：编译管线是公共"编译器基础设施"，语言语义是产品面——符合"语言是契约、契约分层"的原始洞察。
  - 边界：骨架库只收**语义无关**组件（管线/存储/工具）；提取语义留 ph-dsl，发布语义归本 DSL。

---

## 8. 逃逸口（hook）设计——不可妥协

上一轮 review 发现的真实特判证明纯声明无法覆盖全部平台：

| 特判 | 证据 | 说明 |
|---|---|---|
| weibo 级联下拉 + `force=True` 绕过 pointer-events | `weibo/platform.py:1561,1631-1642` | 声明式无法表达 |
| alipay 按钮文案含空格「完 成」 | `alipay/platform.py:1343,1385` | 文本匹配需平台归一 |
| jd 封面 <N bytes 生成临时放大文件 | `jd/platform.py:399,877-922` | 平台特有预处理 |
| channels「确定」非「确认」文案 | `channels/platform.py:603` | 按钮文案差异 |

逃逸口规则：
- `hooks` 允许挂 5 类回调：`before_*` / `after_*` / `custom_step` / `on_error` / `on_retry`
- hook 是 Python 函数，可访问完整 ctx（page/browser/draft）
- **禁止在 hook 里复制 builtin 逻辑**（lint 规则），hook 只做"声明覆盖不了的部分"
- 平台流程文件 = 声明 + hook 引用；hook 实现留在平台目录（不回流 _utils）
- **与 ph-dsl 的差异点**：ph-dsl 是封闭世界（命令 schema 拒绝未知项），发布 DSL 必须开放逃逸口——逃逸口经 CommandAuthority 显式授权，数量纳入评审（借 ph-dsl 的 `CommandAuthorityException` 模式做治理）

---

## 9. 契约测试自动生成（对标 20 个 *_platform_dom.py）

- **静态契约测试**（纯 AST/数据校验，无浏览器）：遍历 registry 所有流程声明，断言——capability 与步骤自洽（`schedule:False` 无 `SetSchedule`）、步骤数据源绑定均有定义、hook 引用存在、禁止裸 `browser.close()`、禁止 `asyncio.get_event_loop()`（对应 review 建议 S8）。**直接复用 ph-dsl 的 check 工具链（§7.2#4）**
- **行为契约测试**：复用现有 DOM 测试基建，从流程声明生成 step 序列化清单，与现有 `*_platform_dom.py` 期望步骤对照（golden 模式）。**可用 ph-dsl 的 IR→NL 指令生成（§7.2#6）产出 golden 文本**
- 现有 20 个 DOM 测试文件保留为真机契约，不删除；新增测试作为回归红线

---

## 10. 版本化与静态校验

- 流程声明文件头带 `schema_version`（对应网站改版周期），builtin 原语集合带版本
- 平台声明版本与 builtin 版本不符 → 启动告警（不是报错，允许灰度）
- 静态校验项：未知原语、重复步骤、capability 冲突、hook 引用缺失、选择器空值——全部进 CI（复用 ph-dsl check 管线或独立脚本，review 建议 S5 的同类机制）。**v0.3 新增：定位器语义优先、后置断言必填、步骤 id 唯一（§11.3）**

---

## 11. AI 作者面协议（v0.3 新增）

> 动机：AI 适合一次性探索（编写/修复），不适合逐次介入（费钱、慢、不确定）。本 DSL 的定位是「AI 产声明、编译器门禁、运行时零 LLM」——AI 是前端（一次性生成），编译器是门禁，运行时是 VM。本节协议保证三件事：AI 产出可安全采纳、修复回路成本收敛、运行时确定性不受影响。协议与语言形态（决策点 1，§14）正交：EDSL 同样需要本节定义的 diff/门禁等价物。

### 11.1 核心原则

| 原则 | 含义 | 违反后果 |
|---|---|---|
| AI 产出只是提案 | 一切 AI 生成的声明/补丁必须过编译门禁（`check` 零诊断）才可执行 | 未验证的 AI 输出进入运行时 |
| 运行时零 LLM | 执行路径（`run_flow`）不含任何模型调用，确定性、可预算 | 成本不可控 + 结果不确定 |
| 双门禁 | 静态门禁（`check`）+ 动态门禁（从失败步骤起重放、postcondition 通过） | 静默错误进入生产 |
| 样本库收敛成本 | 每次（失败快照 + 已验证补丁）入库，同类变化下次直接命中 | 同一漂移反复付 AI 成本 |

### 11.2 工具契约（backend-mcp 新增三个工具）

| 工具 | 输入 | 输出 | 门禁 |
|---|---|---|---|
| `flow-author` | 平台名 + 意图契约 + 参考素材（a11y 树 / 截图 / 旧声明） | flow 声明草案（新平台接入） | `check` 零诊断 + 示例数据 dry-run |
| `flow-repair` | 失败步骤 id + 快照（a11y 树 + 截图 + trace）+ 旧声明 | 最小补丁 diff（仅失败步骤） | `check` 零诊断 + 探针验证通过 |
| `flow-check` | flow 声明 | 诊断报告（静态，无浏览器） | — |

约束：
- 补丁必须是**最小 diff**（按步骤 id 定位，禁止整体重写）——diff 是审计与回滚的最小单元
- 三个工具均有等价 CLI（`flow-check` 即 `parsehub check` 的发布域包装），AI 不是唯一入口

### 11.3 可修复性约束（编译期强制，并入 §10 静态校验）

1. **定位器语义优先**：交互步骤的定位器必须声明语义锚点（`getByRole`/`getByText`/a11y label 或页面文本），CSS 只能作为 fallback 链后续候选——这是 AI 修复成功率的结构性保证：语义定位天然抗漂移，LLM 换定位器成本趋零
2. **后置断言（postcondition）必填**：每步声明成功判据（`wait_for` / url 变化 / 元素出现）；运行时用它判成功，AI 修复用它当 oracle；无断言步骤不允许 `auto-repair`
3. **步骤稳定 id**：id 是 diff/版本化/失败定位的锚点，编译期校验唯一且跨版本稳定
4. 违反 1/2/3 → `check` **报错**（非警告）

### 11.4 修复回路状态机

```
flow 执行 ──失败──▶ 失败分类器（确定性规则：错误类型 + 快照特征）
                        │
        ┌───────────────┼───────────────────┐
        ▼               ▼                   ▼
   选择器漂移        拦截层出现          流程形状变化
   (NoSuchElement)  (新弹窗/登录墙)      (步骤序列不符)
        │               │                   │
        ▼               ▼                   ▼
   flow-repair      flow-repair         AI 接管浏览器重走
   → 换定位器        → 插入跳过步骤        → diff 出新路径
        │               │                   │
        └───────────────┴───────────────────┘
                        ▼
       check 零诊断 + 探针验证（从失败步骤重放，postcondition 通过）
                        ▼
       通过 → 补丁合并 + 样本入库；失败 → 转人工
```

- **失败分类器不调 LLM**：确定性规则，证据 = 错误类型 + 快照特征（是否出现未知弹窗/当前 URL）
- **探针验证**：从失败步骤起重放，该步骤及其后置断言通过即算通过；涉及数据副作用（如发布确认）的步骤走 dry-run/事务性回滚语义（范围见决策点 9，§14）
- **风控/验证码类直接转人工**，永不自动重试硬修（对应 §2 非目标）

### 11.5 成本模型与样本库

| 场景 | LLM 调用 | 说明 |
|---|---|---|
| 新平台接入 | 1 次（`flow-author`） | 一次性编写 |
| 正常执行 | 0 次 | 运行时零 LLM |
| 首次漂移修复 | 1 次（`flow-repair`） | 修复后样本入库 |
| 同类漂移再现 | 0 次 | 命中样本库，直接应用已验证补丁 |

- 样本库 = `data/repair_store/`（gitignored）：key =（平台, 步骤 id, 失败特征哈希）；value =（快照, 补丁, 验证结果, 时间）
- 样本库兼作回归素材：定期抽样重放已验证补丁（对齐 §9 行为契约测试）

---

## 12. 落地路径（三步走）

### Step 1：原语库收敛（先做，独立收益）
- 把 §4 的 9 个原语抽成 `impl/primitives/` 共享运行时，各平台逐步替换重复实现
- 验收：删除 16 份 cookie 解析/13 份 schedule 的重复代码，行为不变（现有 DOM 测试全绿）
- **注意**：不引入 DSL 语法，只收敛函数——这一步本身消灭 ~60% 重复

### Step 2：能力模型 + 会话模型落地
- 引入 `PlatformCapability` 声明，替换 `draft_merge.py:218`、`task_queue.py:261-298`、`image_publish_bp.py:171-183` 的特判
- **引入 ph-dsl 的 Profile/Session 模型（§7.2#1）替代 cookie 三件套**：`check_cookie` → `session verify`（active/stale/revoked），`sync_profile` 对齐 session 元数据
- 前端 `platforms.ts` 通过接口对齐（review 建议 S4）
- 验收：`if platform ==` 类特判归零，capability/session 单一真源

### Step 3：DSL 流程化
- **先定决策点 1**（EDSL vs 文本 DSL + 复用路径 A/B，§14），再选 1-2 个代表性平台（建议 douyin + weibo：一个"标准流"、一个"重特判流"）试点
- 试点通过后批量迁移其余平台，同时接入 §9 测试生成 + §10 静态校验
- 验收：平台目录代码量下降 ≥60%，新平台接入 = 写一份声明 + 补 hook

### Step 4：AI 作者面（最后，依赖 Step 3 试点通过）
- backend-mcp 增加 `flow-author`/`flow-repair`/`flow-check` 三工具（§11.2），先接 repair 回路 + 失败分类器（确定性规则，§11.4）
- 试点平台跑 2 周，以样本库统计修复成功率（§11.5）
- 验收：试点平台漂移修复 ≥70% 自动闭环、运行时 0 LLM 调用、补丁全部可审计回滚

### 与现有 Batch 重构的衔接（顺序约束）
1. **S2 队列三合一（review 建议）必须先于 Step 3 完成**——DSL 只服务单一执行内核；否则 DSL 要适配 publish_executor/task_queue/image 同步三套运行时
2. Step 1 与队列合并互不依赖，可并行
3. Step 2 依赖元数据单源化（S4）的 registry 扩展；会话模型替换与 Step 1 的原语收敛部分重叠（cookie 解析 → session store），建议 Step 2 先行消化
4. Step 4（AI 作者面）依赖 Step 3 的 IR 产物与 check 门禁，序列上排在最后；但 §11.3 可修复性约束（定位器语义优先/后置断言必填）必须在 Step 3 试点时即生效，否则事后补约束会批量改声明

---

## 13. 风险与边界

| 风险 | 缓解 |
|---|---|
| DSL 设计过重（文本语言化倾向） | ph-dsl 骨架复用（§7.4 路径 B）限制自研范围；§12 分三步，每步独立可验收 |
| 逃逸口滥用导致声明形同虚设 | lint 规则禁止 hook 复制 builtin；hook 数量经 CommandAuthority 纳入评审 |
| 选择器漂移是本质约束 | 运行时保持确定性、不解决漂移（本质约束）；处置走离线 AI 修复回路（§11.4）：AI 补丁 + check + 探针验证，成本收敛；风控类人工兜底 |
| 迁移期间双轨并存 | 每平台迁移独立成 PR，DOM 测试全绿才合入 |
| 平台差异超出模型表达能力 | capability 模型 + 逃逸口双保险；模型扩展走评审 |
| **复用 ph-dsl 引入耦合**（路径 A 风险） | 优先路径 B（共享骨架），产品语义彻底分离 |
| AI 补丁引入静默错误 | 双门禁（`check` 零诊断 + 探针验证）+ 最小 diff + 样本库可回滚（§11.4/§11.5） |

---

## 14. 待评审决策点

1. **语言形态与复用路径**（本文 v0.2 核心修正）：
   - 选项 A：EDSL（Python 数据驱动，v0.1 原案）——hook 即函数、mypy 可查，但无编译期契约强校验与 IR 产物
   - 选项 B：**文本 DSL + 复用 ph-dsl 骨架（推荐）**——管线/check/fmt/session 现成，获得编译期契约校验 + IR→文档/测试生成；成本是定义命令集语法
   - 选项 C：库复用 ph-dsl（路径 A，§7.4）——耦合提取语义，不推荐
   - **v0.3 补充判据（AI 可写性）**：文本 DSL（.ph）对 AI 作者面更友好——源码即 diff（补丁干净可审）、语法形式化（AI 生成成功率高于自由 Python 结构）、`check` 门禁现成（AI 输出可被机器裁决）。进一步支撑选项 B；若评审坚持 EDSL，需另行设计 diff 与门禁等价物（§11 协议与语言形态正交）
2. **骨架抽取边界**（若选 B）：ph-dsl 中哪些进共享核心（管线/session store/check/fmt/命令 schema 模式），哪些留 ph-dsl（提取语义/CLI 产品面）
3. **原语集合的边界** —— §4 清单是否够用；`scrape_*_profile` 是否彻底留在平台目录
4. **会话模型替换范围** —— `session verify` 替代 `check_cookie` 是否本期做（涉及 20 个平台 cookie 校验路径）
5. **试点平台** —— 建议 douyin（标准流）+ weibo（重特判流），可换
6. **与队列合并（S2）的排期关系** —— 本文建议 S2 先行，确认是否可接受
7. **测试生成范围** —— 静态契约测试先上，行为 golden 测试是否本期做
8. **AI 作者面范围与排期** —— `flow-repair` 回路是否 Step 3 试点期即并行（建议：是——修复成功率是 DSL 落地价值的关键证据）；`flow-author` 后置于试点通过（§12 Step 4）
9. **探针验证的数据副作用边界** —— 涉及真实发布动作的步骤如何 dry-run（草案：副作用步骤以 postcondition 探测 + 事务性回滚语义处理，需评审确认可接受）

---

## 15. 附录：与既有文档的关系

- 本提案是 `docs/multiplatform-architecture-review-20260822.md` §3 建议（S1-S9）在"平台接入方式"维度的深化
- 落地后需同步更新 `docs/backend-coding-standards.md:39`（新增平台 = impl + bp + registry）为「+ flow 声明」
- 参考实现档案：`/home/dev/ph-dsl`（README、`docs/PROFILES_SESSIONS_ENVIRONMENTS.md`、`docs/DSL_SYNTAX_REFERENCE.md`、`docs/CAPABILITIES.md`、`src/parsehub/compiler.py`）
- v0.3：AI 作者面协议（§11）要求 backend-mcp 暴露 `flow-author`/`flow-repair`/`flow-check`，复用现有 LLM 通道；样本库落 `data/repair_store/`
