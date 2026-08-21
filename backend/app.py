import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# [FIX 2026-06-10] httpx（cloakbrowser 依赖）不支持 SOCKS proxy，系统设置了 ALL_PROXY=socks://
# 会让 cloakbrowser 的 wrapper update check 直接崩。启动时清掉 SOCKS env（保留 HTTP/HTTPS proxy）
for _k in ('ALL_PROXY', 'all_proxy'):
    os.environ.pop(_k, None)

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS

BACKEND_DIR = Path(__file__).parent.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from conf import (
    BASE_DIR,
    FEEDBACK_APP_KEY,
    FEEDBACK_APP_SECRET,
    PLATFORM_MAP,
)
from util._logger import get_channel_logger

logger = get_channel_logger("backend")
if not (FEEDBACK_APP_KEY and FEEDBACK_APP_SECRET):
    logger.warning("[Feedback] 未配置 FEEDBACK_APP_KEY / FEEDBACK_APP_SECRET，反馈系统将返回 503（可在环境变量配置）")

def _ensure_materials_table():
    """服务启动时确保 materials 表存在"""
    DB_PATH = BASE_DIR / "db" / "database.db"
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id TEXT PRIMARY KEY,
            original_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER DEFAULT 0,
            storage_type TEXT NOT NULL DEFAULT 'local',
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            duration REAL DEFAULT 0,
            thumbnail_path TEXT DEFAULT '',
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("[Startup] materials 表已就绪")

_ensure_materials_table()

logger.info(f"[Startup] Python {sys.version} starting...")
logger.info(f"[Startup] Script: {__file__}")
logger.info(f"[Startup] SAU_PORT={os.environ.get('SAU_PORT')}, SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")

app = Flask(__name__)
CORS(app)
# 视频/图片上传不限大小（用户 2026-06-10 明确要求）
# 警告：当前 materials_bp.py:125 用 file.read() 一次性读入内存，超大文件会 OOM
# 如未来需要处理 ≥10GB 文件，应改为流式写入（request.stream → storage.save_stream）
app.config['MAX_CONTENT_LENGTH'] = None

# 注册阶段二扩展 API Blueprint
logger.info("[Startup] Importing ext_api...")
from ext_api import ext_api  # noqa: E402

app.register_blueprint(ext_api)
logger.info("[Startup] ext_api registered OK")

from routes.frames import frames_bp  # noqa: E402

app.register_blueprint(frames_bp)
logger.info("[Startup] frames_bp registered OK")

from blueprints.account_bp import account_bp  # noqa: E402
from blueprints.feedback_bp import feedback_bp  # noqa: E402
from blueprints.image_proxy_bp import image_proxy_bp  # noqa: E402
from blueprints.image_publish_bp import image_publish_bp  # noqa: E402
from blueprints.publish_bp import publish_bp  # noqa: E402

app.register_blueprint(account_bp)
app.register_blueprint(feedback_bp)
app.register_blueprint(image_proxy_bp)
app.register_blueprint(publish_bp)
app.register_blueprint(image_publish_bp)
logger.info("[Startup] image_publish_bp registered OK")

from blueprints.douyin_image_bp import douyin_image_bp  # noqa: E402

app.register_blueprint(douyin_image_bp)
logger.info("[Startup] douyin_image_bp registered OK")

from blueprints.alipay_bp import alipay_bp  # noqa: E402

app.register_blueprint(alipay_bp)
logger.info("[Startup] alipay_bp registered OK")

from blueprints.toutiao_bp import toutiao_bp  # noqa: E402

app.register_blueprint(toutiao_bp)
logger.info("[Startup] toutiao_bp registered OK")

from blueprints.vivo_bp import vivo_bp  # noqa: E402

app.register_blueprint(vivo_bp)
logger.info("[Startup] vivo_bp registered OK")

from blueprints.xiaohongshu_bp import xiaohongshu_bp  # noqa: E402

app.register_blueprint(xiaohongshu_bp)
logger.info("[Startup] xiaohongshu_bp registered OK")

from blueprints.bilibili_bp import bilibili_bp  # noqa: E402

app.register_blueprint(bilibili_bp)
logger.info("[Startup] bilibili_bp registered OK")

from blueprints.weibo_bp import weibo_bp  # noqa: E402

app.register_blueprint(weibo_bp)
logger.info("[Startup] weibo_bp registered OK")

from blueprints.channels_bp import channels_bp  # noqa: E402

app.register_blueprint(channels_bp)
logger.info("[Startup] channels_bp registered OK")

from blueprints.weixin_gzh_bp import weixin_gzh_bp  # noqa: E402

app.register_blueprint(weixin_gzh_bp)
logger.info("[Startup] weixin_gzh_bp registered OK")

from blueprints.materials_bp import materials_bp  # noqa: E402

app.register_blueprint(materials_bp)
logger.info("[Startup] materials_bp registered OK")

from blueprints.kuaishou_image_bp import kuaishou_image_bp  # noqa: E402

app.register_blueprint(kuaishou_image_bp)
logger.info("[Startup] kuaishou_image_bp registered OK")

from blueprints.uploads_bp import uploads_bp  # noqa: E402

app.register_blueprint(uploads_bp)
logger.info("[Startup] uploads_bp registered OK")

from blueprints.taobao_guanghe_bp import taobao_guanghe_bp  # noqa: E402

app.register_blueprint(taobao_guanghe_bp)
logger.info("[Startup] taobao_guanghe_bp registered OK")

from blueprints.jd_bp import bp as jd_bp  # noqa: E402

app.register_blueprint(jd_bp)
logger.info("[Startup] jd_picker registered OK")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
logger.info(f"[Startup] Frontend dir: {FRONTEND_DIR} (exists={FRONTEND_DIR.exists()})")

@app.route('/')
def index():
    if FRONTEND_DIR.exists():
        return send_from_directory(str(FRONTEND_DIR), 'index.html')
    return jsonify({"code": 200, "msg": "API server running"}), 200

@app.route('/assets/<path:filename>')
def custom_static(filename):
    return send_from_directory(str(FRONTEND_DIR / 'assets'), filename)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(str(FRONTEND_DIR), 'favicon.ico')

@app.route('/vite.svg')
def vite_svg():
    return send_from_directory(str(FRONTEND_DIR), 'vite.svg')

@app.route('/changelog/<path:filename>')
def serve_changelog(filename):
    changelog_dir = Path(__file__).parent.parent / "changelog"
    if not changelog_dir.exists():
        changelog_dir = BASE_DIR / "changelog"
    return send_from_directory(str(changelog_dir), filename)

# ── Helper ──────────────────────────────────────────────────

def _get_db_path():
    if data_dir := os.environ.get("SAU_DATA_DIR"):
        return Path(data_dir) / "db" / "database.db"
    return Path(__file__).parent.parent / "data" / "db" / "database.db"

DB_PATH = _get_db_path()

@app.before_request
def _ensure_db():
    db_path = _get_db_path()
    need_init = False
    if not db_path.exists():
        need_init = True
    else:
        try:
            with sqlite3.connect(str(db_path)) as _c:
                _c.execute("SELECT 1 FROM user_info LIMIT 1")
        except sqlite3.OperationalError:
            need_init = True
    if need_init:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from init_db import init_database, migrate_database
            init_database()
            migrate_database()
            logger.info(f"[DB] Initialized database at {db_path}")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[DB] Failed to initialize database: {e}")

@app.before_request
def _before_publish():
    if request.path == '/postVideo' and request.method == 'POST':
        data = request.get_json(silent=True)
        if not data:
            return
        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat()
        batch_id = data.get('batchId') or str(uuid.uuid4())
        detail_id = str(uuid.uuid4())
        platform_type = data.get('type', 0)
        account_list = data.get('accountList', [])
        file_list = data.get('fileList', [])

        account_name = ''
        account_id = data.get('accountId')
        if account_list:
            account_path = account_list[0]
            account_name = data.get('accountName') or Path(account_path).stem or account_path

        # [DEBUG 2026-06-10] 详细日志：把整个请求 body 的关键字段打印出来
        logger.info(
            "[/postVideo REQUEST] batchId=%s account=%s type=%s title=%s fileList=%s videoLandscape.id=%s videoPortrait.id=%s coverLandscape.id=%s coverPortrait.id=%s creationDeclaration=%s aiContent=%s isOriginal=%s category=%s authorStatement=%s compilation=%s scheduleTime=%s enableTimer=%s tags=%s",
            batch_id, account_name, platform_type,
            data.get('title', ''),
            file_list,
            (data.get('videoLandscape') or {}).get('id') if isinstance(data.get('videoLandscape'), dict) else data.get('videoLandscape'),
            (data.get('videoPortrait') or {}).get('id') if isinstance(data.get('videoPortrait'), dict) else data.get('videoPortrait'),
            (data.get('coverLandscape') or {}).get('id') if isinstance(data.get('coverLandscape'), dict) else data.get('coverLandscape'),
            (data.get('coverPortrait') or {}).get('id') if isinstance(data.get('coverPortrait'), dict) else data.get('coverPortrait'),
            data.get('creationDeclaration', ''),
            data.get('aiContent', ''),
            data.get('isOriginal', ''),
            data.get('category', ''),  # 新增：B 站分区字段（platformSettings.zone || 兜底）
            data.get('authorStatement', ''),  # 支付宝作者声明(必填)
            data.get('compilation', ''),  # 支付宝合集(名字)
            data.get('scheduleTime', ''),  # 定时发布
            data.get('enableTimer', ''),
            data.get('tags', ''),
        )

        # account_configs 存：除了 fileList/accountList/type/thumbnail/batchId/accountId/accountName 之外的所有字段
        # 注意：videoMaterialId/landscapeCoverMaterialId/portraitCoverMaterialId 既写 batch 列，也写进 JSON（让 JSON 自包含）
        # 注意：thumbnailLandscape/thumbnailPortrait（抽帧封面路径）也存进 JSON，
        # 供 /api/v2/history 的 _resolve_cover_url 在 material_id 缺失时回退使用
        # 注意：scheduleTime 现在也存进 JSON（spec §2.2 视频结构要求），
        # publish_batches.schedule_time 仍是 batch 级聚合字段，两者并存不冲突
        excluded = {'fileList', 'accountList', 'type', 'thumbnail',
                    'batchId',
                    'accountId', 'accountName'}
        account_configs = {k: v for k, v in data.items() if k not in excluded}

        from services.publish_history import _record_publish
        _record_publish(
            batch_id=batch_id,
            detail_id=detail_id,
            platform=PLATFORM_MAP.get(platform_type, '未知'),
            account_id=account_id,
            account_name=account_name,
            video_path=file_list[0] if file_list else '',
            title=data.get('title', ''),
            description=data.get('description', ''),
            tags=data.get('tags', []),
            status='running',
            started_at=now,
            account_configs=account_configs,
            video_material_id=data.get('videoMaterialId', ''),
            landscape_cover_material_id=data.get('landscapeCoverMaterialId', ''),
            portrait_cover_material_id=data.get('portraitCoverMaterialId', ''),
        )
        g.publish_detail_id = detail_id
        g.publish_start_time = now

@app.after_request
def _after_publish(response):
    if request.path == '/postVideo' and hasattr(g, 'publish_detail_id'):
        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat()
        if response.status_code == 200:
            try:
                resp_data = json.loads(response.get_data(as_text=True))
            except (json.JSONDecodeError, ValueError):
                resp_data = {}
            # 异步化改造后：带 taskId 的 200 只代表「已入队」，publish_details
            # 的最终状态由后台执行线程在发布结束时更新，这里不碰。
            # 其余 200（不应出现）按提交失败兜底。
            if isinstance(resp_data.get('data'), dict) and resp_data['data'].get('taskId'):
                return response
            from services.publish_history import _update_publish_result
            _update_publish_result(g.publish_detail_id, 'failed', now, resp_data.get('msg', '提交失败'))
        else:
            error_msg = ''
            try:
                resp_data = json.loads(response.get_data(as_text=True))
                error_msg = resp_data.get('msg', '')
            except (json.JSONDecodeError, ValueError):
                error_msg = f'HTTP {response.status_code}'
            from services.publish_history import _update_publish_result
            _update_publish_result(g.publish_detail_id, 'failed', now, error_msg)
    return response

# ── Health / diagnostics ────────────────────────────────────

@app.route("/api/health", methods=['GET'])
def health_check():
    import sqlite3 as _sqlite
    diag = {
        "sau_data_dir": os.environ.get("SAU_DATA_DIR"),
        "base_dir": str(BASE_DIR),
        "db_path": str(_get_db_path()),
        "db_exists": _get_db_path().exists(),
        "python": sys.executable,
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
    }
    try:
        with _sqlite.connect(str(_get_db_path())) as _conn:
            count = _conn.execute("SELECT COUNT(*) FROM user_info").fetchone()[0]
            diag["db_user_count"] = count
            diag["db_ok"] = True
    except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        diag["db_ok"] = False
        diag["db_error"] = str(e)
    return jsonify(diag)

# ── Server entry ────────────────────────────────────────────

def find_available_port(start_port=5409, max_attempts=10):
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find available port in range {start_port}-{start_port + max_attempts}")

if __name__ == "__main__":
    import socket

    logger.info("[Startup] Initializing database...")
    from init_db import init_database, migrate_database
    init_database()
    migrate_database()
    logger.info("[Startup] Database initialized OK")

    try:
        import sqlite3 as _sqlite
        _test_path = _get_db_path()
        logger.info(f"[Startup] DB path: {_test_path} (exists={_test_path.exists()})")
        with _sqlite.connect(str(_test_path)) as _conn:
            _conn.execute("SELECT 1 FROM user_info LIMIT 1")
        logger.info("[Startup] DB verification OK")
    except Exception as _e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[Startup] DB verification FAILED: {_e}")
        logger.info(f"[Startup] SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")

    # 启动后台任务：补全存量视频素材 duration=0 的数据，以及缺失 orientation 的数据
    # （草稿/历史恢复走 DB 直读，绕过了「素材库选中→probe」，
    #  导致历史 duration=0 的数据漏识别，发布校验被跳过）
    try:
        from services.duration_repair import start_repair_in_background
        start_repair_in_background()
    except Exception as _e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
        logger.warning("[Startup] 补全任务启动失败（不影响主服务）: %s", _e)

    # 账号登录状态检查机制:如果设置为「启动时检测」,后台异步检测所有账号 cookie
    try:
        _check_mode = "pre-publish"
        try:
            with _sqlite.connect(str(_get_db_path())) as _c:
                _row = _c.execute("SELECT value FROM settings WHERE key='accountCheckMode'").fetchone()
                if _row:
                    _check_mode = _row[0]
        except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
            pass
        if _check_mode == "startup":
            logger.info("[Startup] 账号检查模式=启动时检测,开始后台异步检测所有账号...")
            import threading as _threading

            def _check_all_accounts():
                import asyncio as _asyncio
                import sqlite3 as _sqlite
                try:
                    db_path = _get_db_path()
                    with _sqlite.connect(str(db_path)) as conn:
                        rows = conn.execute(
                            "SELECT id, type, filePath, userName FROM user_info"
                        ).fetchall()
                    logger.info(f"[Startup] 共 {len(rows)} 个账号待检测")
                    from impl.registry import get_platform
                    for row in rows:
                        acc_id, acc_type, cookie_file, nick = row
                        try:
                            platform = get_platform(acc_type)
                            if not platform:
                                continue
                            cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
                            if not Path(cookie_path).exists():
                                with _sqlite.connect(str(db_path)) as conn:
                                    conn.execute(
                                        "UPDATE user_info SET status=0 WHERE id=?",
                                        (acc_id,),
                                    )
                                    conn.commit()
                                logger.info(f"[Startup] 账号 {nick}(id={acc_id}) cookie 文件不存在,标记无效")
                                continue
                            ok = _asyncio.run(platform.check_cookie(cookie_file))
                            new_status = 1 if ok else 0
                            with _sqlite.connect(str(db_path)) as conn:
                                conn.execute(
                                    "UPDATE user_info SET status=? WHERE id=?",
                                    (new_status, acc_id),
                                )
                                conn.commit()
                            logger.info(f"[Startup] 账号 {nick}(id={acc_id}) 检测完成: {'有效' if ok else '无效'}")
                        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                            logger.info(f"[Startup] 账号 {nick}(id={acc_id}) 检测异常: {e}")
                    logger.info("[Startup] 所有账号检测完成")
                except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info(f"[Startup] 账号检测线程异常: {e}")

            _t = _threading.Thread(target=_check_all_accounts, daemon=True)
            _t.start()
            logger.info("[Startup] 账号检测后台线程已启动")
        else:
            logger.info("[Startup] 账号检查模式=发布前检测,跳过启动时检测")
    except Exception as _e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
        logger.warning("[Startup] 账号检查模式读取失败（不影响主服务）: %s", _e)

    port = int(os.environ.get("SAU_PORT", "5409"))
    if port == 5409:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
        except OSError:
            port = find_available_port(5409 + 1)
            logger.info(f"[Startup] Port 5409 in use, using port {port}")
    logger.info(f"[Startup] Starting Waitress server on port {port}")
    from waitress import serve
    os.environ["SAU_PORT"] = str(port)
    # threads=16：默认 4 线程会被「并发 checkCookie + 多个 SSE /login 长连接」
    # 占满，导致后端假死。加大线程池让两者不再互相挤占。
    serve(app, host="0.0.0.0", port=port, threads=16)
