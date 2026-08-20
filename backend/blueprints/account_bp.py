"""账号管理 Blueprint：账号 CRUD + 标签管理 + Cookie 文件上传下载。

从 app.py 单体迁移（Phase 2 收敛），行为与迁移前一致。
"""
import asyncio
import random
import sqlite3
import sys
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
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
    except Exception as e:
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
                except Exception:
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
    except Exception as e:
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
                    except Exception as e:
                        logger.info(f"[WARN] 删除Cookie文件失败: {e}")

            cursor.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
            conn.commit()

        return jsonify({"code": 200, "msg": "account deleted successfully", "data": None}), 200
    except Exception as e:
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
    except Exception:
        return jsonify({"code": 500, "msg": "update failed!", "data": None}), 500


# ── Tag management ────────────────────────────────────────

@account_bp.route('/api/tags', methods=['GET'])
def get_tags():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM tags ORDER BY name').fetchall()
        return jsonify({"code": 200, "data": [dict(r) for r in rows]})
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        return jsonify({"code": 500, "msg": f"下载Cookie文件失败: {e!s}", "data": None}), 500
