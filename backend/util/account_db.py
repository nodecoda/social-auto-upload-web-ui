"""账号 DB 查询共享工具（架构整改：_get_account_cookie_file 10 个 blueprint 复制收敛）。

原先 10 个 blueprint 各自内联 `_get_account_cookie_file`，仅平台 type 号不同。
id 为 user_info 表主键（全局唯一），故 account_id 分支无需再带 type 过滤，
weibo/kuaishou 原实现中的冗余 type 条件与本函数行为等价。
"""
import sqlite3
from pathlib import Path

from conf import BASE_DIR

_DB_PATH = Path(BASE_DIR / "db" / "database.db")


def get_account_cookie_file(account_id, platform_type=None):
    """从 user_info 表取 cookie 文件名。

    - ``account_id`` 有值 → 按主键 id 精确查
    - ``account_id`` 为空 → 取指定平台(type)任一个账号（platform_type 必传）
    - 查不到返回 None
    """
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        cursor = conn.cursor()
        if account_id:
            cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
        else:
            cursor.execute(
                "SELECT filePath FROM user_info WHERE type = ? LIMIT 1",
                (platform_type,),
            )
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()
