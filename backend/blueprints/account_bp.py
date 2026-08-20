"""账号管理 Blueprint：账号 CRUD + 标签管理 + Cookie 文件上传下载。

从 app.py 单体迁移（Phase 2 收敛），行为与迁移前一致。
"""
import asyncio
import json
import random
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path
from queue import Queue

from flask import Blueprint, Response, jsonify, request, send_from_directory

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR, PLATFORM_MAP
from impl.registry import get_platform
from util._logger import get_channel_logger

logger = get_channel_logger("account")

account_bp = Blueprint('account', __name__)

DB_PATH = BASE_DIR / "db" / "database.db"

@account_bp.route("/getAccounts", methods=['GET'])
def getAccounts():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_info')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

            for row in rows_list:
                tags = conn.execute('''
                    SELECT t.id, t.name, t.color FROM tags t
                    JOIN account_tags at ON t.id = at.tag_id
                    WHERE at.account_id = ?
                ''', (row[0],)).fetchall()
                row.append([dict(t) for t in tags])

        return jsonify({"code": 200, "msg": None, "data": rows_list}), 200
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": f"获取账号列表失败: {e!s}", "data": None}), 500


@account_bp.route("/getValidAccounts", methods=['GET'])
def getValidAccounts():
    """获取所有账号并使用新引擎逐个验证 cookie 有效性"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_info')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

        for row in rows_list:
            platform = get_platform(row[1])
            if platform:
                try:
                    valid = asyncio.run(platform.check_cookie(row[2]))
                except Exception:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
                    valid = False
                new_status = 1 if valid else 0
                row[4] = new_status
                with sqlite3.connect(str(DB_PATH)) as conn:
                    conn.execute('UPDATE user_info SET status = ? WHERE id = ?', (new_status, row[0]))

        with sqlite3.connect(str(DB_PATH)) as conn:
            for row in rows_list:
                tags = conn.execute('''
                    SELECT t.id, t.name, t.color FROM tags t
                    JOIN account_tags at ON t.id = at.tag_id
                    WHERE at.account_id = ?
                ''', (row[0],)).fetchall()
                row.append([dict(t) for t in tags])

        return jsonify({"code": 200, "msg": None, "data": rows_list}), 200
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": f"获取账号列表失败: {e!s}", "data": None}), 500


@account_bp.route('/deleteAccount', methods=['DELETE'])
def delete_account():
    account_id = request.args.get('id')
    if not account_id or not account_id.isdigit():
        return jsonify({"code": 400, "msg": "Invalid or missing account ID", "data": None}), 400

    account_id = int(account_id)
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_info WHERE id = ?", (account_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({"code": 404, "msg": "account not found", "data": None}), 404

            record = dict(record)
            if record.get('filePath'):
                cookie_file_path = Path(BASE_DIR / "cookiesFile" / record['filePath'])
                if cookie_file_path.exists():
                    try:
                        cookie_file_path.unlink()
                    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                        logger.info(f"[WARN] 删除Cookie文件失败: {e}")

            cursor.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
            conn.commit()

        return jsonify({"code": 200, "msg": "account deleted successfully", "data": None}), 200
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": f"delete failed: {e!s}", "data": None}), 500


@account_bp.route('/updateUserinfo', methods=['POST'])
def updateUserinfo():
    data = request.get_json()
    user_id = data.get('id')
    type_ = data.get('type')
    userName = data.get('userName')
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                'UPDATE user_info SET type = ?, userName = ? WHERE id = ?',
                (type_, userName, user_id)
            )
            conn.commit()
        return jsonify({"code": 200, "msg": "account update successfully", "data": None}), 200
    except Exception:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": "update failed!", "data": None}), 500


# ── Tag management ────────────────────────────────────────

@account_bp.route('/api/tags', methods=['GET'])
def get_tags():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM tags ORDER BY name').fetchall()
        return jsonify({"code": 200, "data": [dict(r) for r in rows]})
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": str(e)}), 500


@account_bp.route('/api/tags', methods=['POST'])
def create_tag():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    color = data.get('color') or random.choice([
        '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e',
        '#f97316', '#f59e0b', '#10b981', '#14b8a6',
        '#0ea5e9', '#3b82f6',
    ])
    if not name:
        return jsonify({"code": 400, "msg": "标签名不能为空"}), 400
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('INSERT INTO tags (name, color) VALUES (?, ?)', (name, color))
            tag_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.commit()
        return jsonify({"code": 200, "data": {"id": tag_id, "name": name, "color": color}})
    except sqlite3.IntegrityError:
        return jsonify({"code": 409, "msg": "标签名已存在"}), 409
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": str(e)}), 500


@account_bp.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            # SQLite 默认不强制外键,需要先清关联行
            conn.execute('DELETE FROM account_tags WHERE tag_id = ?', (tag_id,))
            conn.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
            conn.commit()
        return jsonify({"code": 200})
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": str(e)}), 500


@account_bp.route('/api/accounts/<int:account_id>/tags', methods=['PUT'])
def set_account_tags(account_id):
    data = request.get_json()
    tag_ids = data.get('tag_ids', [])
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('DELETE FROM account_tags WHERE account_id = ?', (account_id,))
            for tid in tag_ids:
                conn.execute('INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)', (account_id, tid))
            conn.commit()
        return jsonify({"code": 200})
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": str(e)}), 500


@account_bp.route('/api/accounts/batch/tags', methods=['PUT'])
def set_batch_account_tags():
    """批量为多个账号添加相同的标签(追加模式:不清除已有标签)"""
    data = request.get_json()
    account_ids = data.get('account_ids', [])
    tag_ids = data.get('tag_ids', [])
    if not account_ids:
        return jsonify({"code": 400, "msg": "请选择至少一个账号"}), 400
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            for account_id in account_ids:
                for tid in tag_ids:
                    conn.execute('INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)', (account_id, tid))
            conn.commit()
        return jsonify({"code": 200, "data": {"updated": len(account_ids)}})
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": str(e)}), 500


@account_bp.route('/api/accounts/<int:account_id>/tags', methods=['GET'])
def get_account_tags(account_id):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('''
                SELECT t.* FROM tags t
                JOIN account_tags at ON t.id = at.tag_id
                WHERE at.account_id = ?
                ORDER BY t.name
            ''', (account_id,)).fetchall()
        return jsonify({"code": 200, "data": [dict(r) for r in rows]})
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": str(e)}), 500


# ── Cookie file management ──────────────────────────────────

@account_bp.route('/uploadCookie', methods=['POST'])
def upload_cookie():
    try:
        if 'file' not in request.files:
            return jsonify({"code": 400, "msg": "没有找到Cookie文件", "data": None}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"code": 400, "msg": "Cookie文件名不能为空", "data": None}), 400
        if not file.filename.endswith('.json'):
            return jsonify({"code": 400, "msg": "Cookie文件必须是JSON格式", "data": None}), 400

        account_id = request.form.get('id')
        platform = request.form.get('platform')
        if not account_id or not platform:
            return jsonify({"code": 400, "msg": "缺少账号ID或平台信息", "data": None}), 400

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT filePath FROM user_info WHERE id = ?', (account_id,))
            result = cursor.fetchone()

        if not result:
            return jsonify({"code": 404, "msg": "账号不存在", "data": None}), 404

        cookie_file_path = Path(BASE_DIR / "cookiesFile" / result['filePath'])
        cookie_file_path.parent.mkdir(parents=True, exist_ok=True)
        file.save(str(cookie_file_path))

        return jsonify({"code": 200, "msg": "Cookie文件上传成功", "data": None}), 200
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": f"上传Cookie文件失败: {e!s}", "data": None}), 500


@account_bp.route('/downloadCookie', methods=['GET'])
def download_cookie():
    try:
        file_path = request.args.get('filePath')
        if not file_path:
            return jsonify({"code": 400, "msg": "缺少文件路径参数", "data": None}), 400

        cookie_file_path = Path(BASE_DIR / "cookiesFile" / file_path).resolve()
        base_path = Path(BASE_DIR / "cookiesFile").resolve()

        if not cookie_file_path.is_relative_to(base_path):
            return jsonify({"code": 400, "msg": "非法文件路径", "data": None}), 400
        if not cookie_file_path.exists():
            return jsonify({"code": 404, "msg": "Cookie文件不存在", "data": None}), 404

        return send_from_directory(
            directory=str(cookie_file_path.parent),
            path=cookie_file_path.name,
            as_attachment=True
        )
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return jsonify({"code": 500, "msg": f"下载Cookie文件失败: {e!s}", "data": None}), 500

# ─────────────────────────────────────────────────────────────────────────────
# 账号域收尾迁移(Phase 3):checkAccount / syncProfile / 登录 SSE / Cookie 导入
# 从 app.py 迁移,URL 路径与行为保持迁移前一致。
# ─────────────────────────────────────────────────────────────────────────────

# SSE 登录状态队列(keyed by account id);与 /importAccount 共用 sse_stream 协议
active_queues: dict[str, Queue] = {}


def _is_terminal_login_sse_message(message: str) -> bool:
    if message in {"200", "500"}:
        return True
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return False
    return str(payload.get("status", "")).lower() in {"200", "500", "0", "error"}


def sse_stream(status_queue):
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
            if _is_terminal_login_sse_message(msg):
                break
        else:
            time.sleep(0.1)


def _get_account_record(account_id):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user_info WHERE id = ?', (account_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


@account_bp.route('/checkAccount', methods=['GET'])
def check_account():
    account_id = request.args.get('id')
    if not account_id or not account_id.isdigit():
        return jsonify({"code": 400, "msg": "无效的账号ID"}), 400

    record = _get_account_record(int(account_id))
    if not record:
        return jsonify({"code": 404, "msg": "账号不存在"}), 404

    platform = get_platform(record['type'])
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    valid = asyncio.run(platform.check_cookie(record['filePath']))
    new_status = 1 if valid else 0
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute('UPDATE user_info SET status = ? WHERE id = ?', (new_status, record['id']))

    msg = "Cookie 有效" if valid else "Cookie 已失效，请重新登录"
    return jsonify({"code": 200, "msg": msg, "data": {"id": record['id'], "status": new_status, "valid": valid}})


@account_bp.route('/syncProfile', methods=['POST'])
def sync_profile():
    account_id = request.json.get('id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少账号ID", "data": None}), 400

    record = _get_account_record(account_id)
    if not record:
        return jsonify({"code": 404, "msg": "账号不存在", "data": None}), 404

    platform = get_platform(record['type'])
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型", "data": None}), 400

    # sync_profile 新约定:返回 dict{name, avatar, stats}
    # 兼容旧实现:返回 2 元组 (name, avatar) 时 stats 为 []
    result = asyncio.run(platform.sync_profile(record['filePath']))
    if isinstance(result, dict):
        name = result.get('name', '') or ''
        avatar = result.get('avatar', '') or ''
        stats = result.get('stats', []) or []
        if not isinstance(stats, list):
            stats = []
    elif isinstance(result, tuple):
        name = result[0] if len(result) > 0 else ''
        avatar = result[1] if len(result) > 1 else ''
        stats = []
    else:
        name, avatar, stats = '', '', []

    if name or avatar:
        stats_json = json.dumps(stats, ensure_ascii=False)
        with sqlite3.connect(str(DB_PATH)) as conn:
            if name:
                conn.execute(
                    'UPDATE user_info SET userName = ?, avatar = ?, stats = ? WHERE id = ?',
                    (name, avatar, stats_json, account_id),
                )
            else:
                conn.execute(
                    'UPDATE user_info SET avatar = ?, stats = ? WHERE id = ?',
                    (avatar, stats_json, account_id),
                )

    return jsonify({
        "code": 200, "msg": "同步成功",
        "data": {"name": name, "avatar": avatar, "stats": stats},
    })


@account_bp.route('/openCreatorCenter', methods=['POST'])
def open_creator_center():
    account_id = request.json.get('id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少账号ID"}), 400

    record = _get_account_record(account_id)
    if not record:
        return jsonify({"code": 404, "msg": "账号不存在"}), 404

    platform = get_platform(record['type'])
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    thread = threading.Thread(
        target=lambda: asyncio.run(platform.open_creator_center(record['filePath'])),
        daemon=True
    )
    thread.start()
    return jsonify({"code": 200, "msg": "正在打开创作中心"})


@account_bp.route('/login')
def login():
    type_str = request.args.get('type')
    id_str = request.args.get('id')
    account_id = request.args.get('account_id')
    if not type_str or not id_str:
        return jsonify({"code": 400, "msg": "缺少 type 或 id"}), 400

    platform = get_platform(int(type_str))
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    status_queue = Queue()
    active_queues[id_str] = status_queue

    def _cleanup():
        active_queues.pop(id_str, None)

    def _run_login():
        try:
            asyncio.run(platform.login(id_str, status_queue, account_id=account_id))
        except asyncio.CancelledError:
            logger.info(f"[login] 用户关闭了浏览器，{platform.platform_name} 登录取消")
            status_queue.put(json.dumps({"status": "error", "msg": "用户关闭了浏览器"}))

    thread = threading.Thread(
        target=_run_login,
        daemon=True
    )
    thread.start()

    response = Response(sse_stream(status_queue), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Content-Type'] = 'text/event-stream'
    response.call_on_close(_cleanup)
    return response


@account_bp.route('/platforms/import-supported', methods=['GET'])
def platforms_import_supported():
    """列出所有支持 cookie 字符串导入的平台。

    返回精简字段，前端用来渲染「导入用户」弹窗的平台选择下拉。
    """
    out = []
    for pid in sorted(PLATFORM_MAP.keys()):
        p = get_platform(pid)
        if p is None or not getattr(p, "supports_cookie_import", False):
            continue
        out.append({
            "id": pid,
            "key": p.platform_key,
            "name": p.platform_name,
            "letter": (p.platform_name[:1] if p.platform_name else ""),
        })
    return jsonify({"code": 200, "msg": "ok", "data": out}), 200


# 导入任务的 task_id → status_queue；与 /login 共用 SSE 协议
import_active_queues: dict[str, Queue] = {}


@account_bp.route('/importAccount', methods=['POST'])
def import_account_start():
    """启动一个 cookie 导入任务。

    Request body (JSON):
        type:        platform_id (int)
        cookie_str:  浏览器导出的 'k=v; k=v' 字符串
        account_id:  可选；已存在账号的 id（re-import 时更新 cookie 文件）

    Response:
        {"code": 200, "msg": "ok", "data": {"task_id": "..."}}

    前端拿到 task_id 后再 EventSource('/importAccount/stream?task_id=...') 拉进度。
    """
    data = request.get_json(silent=True) or {}
    type_raw = data.get('type')
    cookie_str = (data.get('cookie_str') or '').strip()
    account_id_raw = data.get('account_id')

    if type_raw is None or not cookie_str:
        return jsonify({
            "code": 400, "msg": "缺少 type 或 cookie_str", "data": None,
        }), 400

    try:
        type_int = int(type_raw)
    except (TypeError, ValueError):
        return jsonify({
            "code": 400, "msg": "type 必须是整数", "data": None,
        }), 400

    platform = get_platform(type_int)
    if platform is None:
        return jsonify({
            "code": 400, "msg": "不支持的平台", "data": None,
        }), 400
    if not getattr(platform, "supports_cookie_import", False):
        return jsonify({
            "code": 400, "msg": f"{platform.platform_name} 暂不支持 cookie 导入",
            "data": None,
        }), 400

    account_id = None
    if account_id_raw is not None and str(account_id_raw).strip():
        try:
            account_id = int(account_id_raw)
        except (TypeError, ValueError):
            return jsonify({
                "code": 400, "msg": "account_id 必须是整数", "data": None,
            }), 400

    task_id = uuid.uuid4().hex
    status_queue: Queue = Queue()
    import_active_queues[task_id] = status_queue

    def _cleanup():
        import_active_queues.pop(task_id, None)

    def _run_import():
        try:
            asyncio.run(platform.import_cookie(
                cookie_str, status_queue, account_id=account_id,
            ))
        except asyncio.CancelledError:
            status_queue.put(json.dumps({
                "status": "error", "step": 0, "msg": "任务被取消",
            }))
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            # import_cookie 内部已经把 error 推过 queue 了；这里是兜底
            logger.info(f"[importAccount] 未捕获异常: {e}")
            try:
                status_queue.put(json.dumps({
                    "status": "error", "step": 0, "msg": str(e),
                }))
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass

    thread = threading.Thread(target=_run_import, daemon=True)
    thread.start()

    return jsonify({
        "code": 200, "msg": "ok",
        "data": {"task_id": task_id},
    }), 200


@account_bp.route('/importAccount/stream', methods=['GET'])
def import_account_stream():
    """SSE 推送 cookie 导入进度。"""
    task_id = request.args.get('task_id')
    if not task_id or task_id not in import_active_queues:
        return jsonify({
            "code": 404, "msg": "task 不存在或已结束", "data": None,
        }), 404

    status_queue = import_active_queues[task_id]

    def _cleanup():
        import_active_queues.pop(task_id, None)

    response = Response(
        sse_stream(status_queue), mimetype='text/event-stream',
    )
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Content-Type'] = 'text/event-stream'
    response.call_on_close(_cleanup)
    return response
