"""注册表全量契约测试（R1 — 架构整改清单首项）。

把架构 review（docs/architecture-rectification-roi.md R1）发现的
行为层漂移变成 CI 红线：

- 结构契约：注册表内所有平台均为 BasePlatform 子类、元数据完整、key 唯一
- 文件级红线：平台目录禁止直接 `browser.close()` / `asyncio.get_event_loop()`
  （浏览器生命周期必须走基类 self.close_browser / self.create_browser）
- 发布契约：sync 平台 publish_video 的 asyncio.run 必须被 try 包裹
  （否则异常被吞 = 静默发布失败；R2 修复目标，当前 0 违规）

注意：只扫「已注册」平台（registry._registry），不扫 impl/ 下全部模块
（jd 不单独注册，由 jingmai 委托，不算独立平台）。
"""
import ast
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import impl.registry as registry
from impl.base_platform import BasePlatform

IMPL_DIR = Path(__file__).parent.parent / "impl"


def _registered_platforms():
    return sorted(registry._registry.values(), key=lambda cls: cls.platform_id)


# ---------------------------------------------------------------------------
# 结构契约
# ---------------------------------------------------------------------------

def test_all_registered_are_baseplatform_subclasses():
    for cls in _registered_platforms():
        assert issubclass(cls, BasePlatform), f"platform {cls.platform_id} {cls.__name__} 不是 BasePlatform 子类"


def test_all_registered_have_metadata():
    for cls in _registered_platforms():
        assert isinstance(getattr(cls, "platform_id", None), int), f"{cls.__name__} 缺 platform_id"
        assert isinstance(getattr(cls, "platform_key", None), str) and cls.platform_key, f"{cls.__name__} 缺 platform_key"
        assert isinstance(getattr(cls, "platform_name", None), str) and cls.platform_name, f"{cls.__name__} 缺 platform_name"


def test_platform_keys_unique():
    keys = [cls.platform_key for cls in _registered_platforms()]
    assert len(keys) == len(set(keys)), "platform_key 存在重复"


# ---------------------------------------------------------------------------
# 文件级红线：浏览器生命周期
# ---------------------------------------------------------------------------

def _platform_sources():
    """返回 {源文件路径: AST}，仅限已注册平台。"""
    out = {}
    for cls in _registered_platforms():
        mod = inspect.getmodule(cls)
        if mod is None or not mod.__file__:
            continue
        path = Path(mod.__file__)
        if "impl" not in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                child.parent = parent
        out[path] = tree
    return out


def test_no_direct_browser_close_in_platform_sources():
    """平台源码禁止直接 browser.close()——必须走基类 self.close_browser。"""
    offenders = []
    for path, tree in _platform_sources().items():
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "close" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "browser"):
                offenders.append(f"{path.relative_to(IMPL_DIR)}:{node.lineno}")
    assert not offenders, f"平台源码直接调用 browser.close()（应走 self.close_browser）: {offenders}"


def test_no_asyncio_get_event_loop_in_platform_sources():
    """平台源码禁止 asyncio.get_event_loop()（async 上下文中 3.12 起弃用/报错）。"""
    offenders = []
    for path, tree in _platform_sources().items():
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get_event_loop" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "asyncio"):
                offenders.append(f"{path.relative_to(IMPL_DIR)}:{node.lineno}")
    assert not offenders, f"平台源码使用 asyncio.get_event_loop()（已弃用）: {offenders}"


# ---------------------------------------------------------------------------
# 发布契约：sync 平台不得吞失败
# ---------------------------------------------------------------------------

def test_no_sync_publish_video_swallow_failure():
    """sync publish_video 的 asyncio.run 必须被 try 包裹。

    判定：方法非 async、含 asyncio.run 调用，且该 run 不在 try 块内 → 违规。
    R2 修复后期望 0 违规；违规说明发布异常被静默吞掉（返回成功）。
    """
    violations = []
    for path, tree in _platform_sources().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "publish_video":
                runs = [
                    n for n in ast.walk(node)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "run" and isinstance(n.func.value, ast.Name)
                    and n.func.value.id in ("asyncio", "_aio")
                ]
                for run in runs:
                    in_try = False
                    parent = run
                    while parent is not None:
                        if isinstance(parent, ast.Try):
                            in_try = True
                            break
                        parent = getattr(parent, "parent", None)
                    if not in_try:
                        violations.append(f"{path.relative_to(IMPL_DIR)}:{run.lineno}")
    assert not violations, (
        f"sync publish_video 存在吞失败反模式（asyncio.run 异常未被捕获），"
        f"应在 run 外加 try/except 返回 False: {violations}"
    )
