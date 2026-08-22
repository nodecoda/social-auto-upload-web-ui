"""异步编排共享工具（架构整改：run_async 9 处重复收敛）。

原 9 个 blueprint 各自复制一份 run_async，且使用已弃用的
``asyncio.get_event_loop().is_running()``（Python 3.12+ 弃用告警）。
此处收敛为单一实现，用 ``get_running_loop()`` 探测：
- 当前线程无运行中事件循环 → 直接 ``asyncio.run``
- 当前线程已有事件循环（如 Flask 测试上下文）→ 起一次性线程跑新循环，避免复用冲突
"""
import asyncio
import threading


def run_async(coro):
    """在任意线程里安全执行协程，返回其返回值（无运行中循环直接 asyncio.run）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 无运行中事件循环（普通 Flask 请求线程）——直接 asyncio.run
        return asyncio.run(coro)
    # 已有运行中循环（可能是测试/嵌套上下文）——起一次性线程跑新循环，
    # 与旧实现行为一致（旧实现同样 new_event_loop + run_until_complete）
    result = {}

    def _run():
        new_loop = asyncio.new_event_loop()
        try:
            result["v"] = new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    return result.get("v")
