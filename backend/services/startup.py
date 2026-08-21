"""启动期后台任务（自 app.py __main__ 抽离，行为等价）。

职责：
- start_duration_repair(): 补全存量素材 duration/orientation 数据
- maybe_start_account_check(): 按 settings.accountCheckMode 决定是否后台检测账号 cookie

db 路径统一由调用方注入（app.py 的 _get_db_path），保持运行时读取
SAU_DATA_DIR 的语义不变，也便于测试注入。
"""

import asyncio
import sqlite3
import threading
from pathlib import Path

from conf import BASE_DIR
from util._logger import get_channel_logger

logger = get_channel_logger("startup")


def start_duration_repair() -> None:
    """补全存量视频素材 duration=0 / 缺失 orientation 的数据（后台线程，失败不影响主服务）。"""
    try:
        from services.duration_repair import start_repair_in_background

        start_repair_in_background()
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
        logger.warning("[Startup] 补全任务启动失败（不影响主服务）: %s", e)


def maybe_start_account_check(get_db_path) -> None:
    """账号登录状态检查：若 settings.accountCheckMode == 'startup'，后台异步检测全部账号 cookie。

    Args:
        get_db_path: 零参可调用，返回 SQLite 数据库路径（运行时求值）。
    """
    try:
        check_mode = "pre-publish"
        try:
            with sqlite3.connect(str(get_db_path())) as _c:
                _row = _c.execute("SELECT value FROM settings WHERE key='accountCheckMode'").fetchone()
                if _row:
                    check_mode = _row[0]
        except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
            pass
        if check_mode != "startup":
            logger.info("[Startup] 账号检查模式=发布前检测,跳过启动时检测")
            return
        logger.info("[Startup] 账号检查模式=启动时检测,开始后台异步检测所有账号...")
        _t = threading.Thread(target=_check_all_accounts, args=(get_db_path,), daemon=True)
        _t.start()
        logger.info("[Startup] 账号检测后台线程已启动")
    except Exception as _e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
        logger.warning("[Startup] 账号检查模式读取失败（不影响主服务）: %s", _e)


def _check_all_accounts(get_db_path) -> None:
    """后台线程体：逐账号校验 cookie，缺失/无效则更新 user_info.status。"""
    try:
        with sqlite3.connect(str(get_db_path())) as conn:
            rows = conn.execute("SELECT id, type, filePath, userName FROM user_info").fetchall()
        logger.info("[Startup] 共 %d 个账号待检测", len(rows))
        from impl.registry import get_platform

        for acc_id, acc_type, cookie_file, nick in rows:
            try:
                platform = get_platform(acc_type)
                if not platform:
                    continue
                cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
                if not Path(cookie_path).exists():
                    with sqlite3.connect(str(get_db_path())) as conn:
                        conn.execute("UPDATE user_info SET status=0 WHERE id=?", (acc_id,))
                        conn.commit()
                    logger.info("[Startup] 账号 %s(id=%s) cookie 文件不存在,标记无效", nick, acc_id)
                    continue
                ok = asyncio.run(platform.check_cookie(cookie_file))
                new_status = 1 if ok else 0
                with sqlite3.connect(str(get_db_path())) as conn:
                    conn.execute("UPDATE user_info SET status=? WHERE id=?", (new_status, acc_id))
                    conn.commit()
                logger.info("[Startup] 账号 %s(id=%s) 检测完成: %s", nick, acc_id, "有效" if ok else "无效")
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.info("[Startup] 账号 %s(id=%s) 检测异常: %s", nick, acc_id, e)
        logger.info("[Startup] 所有账号检测完成")
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info("[Startup] 账号检测线程异常: %s", e)
