import importlib
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

# 启动即初始化数据库完整 schema（幂等：CREATE IF NOT EXISTS + 增量迁移）。
# 历史：materials 表曾在此单独建（_ensure_materials_table），与 init_db.py 重复定义
# 且缺失 orientation 列（双源真相）——现已统一到 init_db.py 单一建表入口，删除本处重复。
from init_db import init_database, migrate_database

init_database()
migrate_database()

logger.info(f"[Startup] Python {sys.version} starting...")
logger.info(f"[Startup] Script: {__file__}")
logger.info(f"[Startup] SAU_PORT={os.environ.get('SAU_PORT')}, SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")

app = Flask(__name__)
CORS(app)
# 视频/图片上传不限大小（用户 2026-06-10 明确要求）。
# 上传链路已流式化：materials_bp 按 CHUNK_SIZE 分块读 file.stream → storage.save_stream，
# 分片上传走 upload_sessions/upload_chunks 断点续传，均不会整文件读入内存。
app.config['MAX_CONTENT_LENGTH'] = None

# 注册全部 Blueprint。顺序 = 历史注册顺序（Flask 按注册序匹配 URL 规则，须保持一致）。
_BLUEPRINT_SPECS = [
    # (模块路径, blueprint 变量名)
    ("ext_api", "ext_api"),
    ("routes.frames", "frames_bp"),
    ("blueprints.account_bp", "account_bp"),
    ("blueprints.feedback_bp", "feedback_bp"),
    ("blueprints.image_proxy_bp", "image_proxy_bp"),
    ("blueprints.image_publish_bp", "image_publish_bp"),
    ("blueprints.publish_bp", "publish_bp"),
    ("blueprints.douyin_image_bp", "douyin_image_bp"),
    ("blueprints.alipay_bp", "alipay_bp"),
    ("blueprints.toutiao_bp", "toutiao_bp"),
    ("blueprints.vivo_bp", "vivo_bp"),
    ("blueprints.xiaohongshu_bp", "xiaohongshu_bp"),
    ("blueprints.bilibili_bp", "bilibili_bp"),
    ("blueprints.weibo_bp", "weibo_bp"),
    ("blueprints.channels_bp", "channels_bp"),
    ("blueprints.weixin_gzh_bp", "weixin_gzh_bp"),
    ("blueprints.materials_bp", "materials_bp"),
    ("blueprints.kuaishou_image_bp", "kuaishou_image_bp"),
    ("blueprints.uploads_bp", "uploads_bp"),
    ("blueprints.taobao_guanghe_bp", "taobao_guanghe_bp"),
    ("blueprints.jd_bp", "jd_bp"),
]


def _register_blueprints(target_app) -> None:
    """按清单导入并注册全部 Blueprint（显式顺序，避免逐个手写 import+register）。"""
    for module_name, attr_name in _BLUEPRINT_SPECS:
        module = importlib.import_module(module_name)
        target_app.register_blueprint(getattr(module, attr_name))
        logger.info("[Startup] %s registered OK", attr_name)


logger.info("[Startup] Importing %d blueprints...", len(_BLUEPRINT_SPECS))
_register_blueprints(app)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
logger.info(f"[Startup] Frontend dir: {FRONTEND_DIR} (exists={FRONTEND_DIR.exists()})")

@app.route('/')
def index():
    """前端 SPA 入口：返回 frontend/dist/index.html（不存在则报 API 存活）。"""
    if FRONTEND_DIR.exists():
        return send_from_directory(str(FRONTEND_DIR), 'index.html')
    return jsonify({"code": 200, "msg": "API server running"}), 200

@app.route('/assets/<path:filename>')
def custom_static(filename):
    """前端构建产物静态资源（frontend/dist/assets）。"""
    return send_from_directory(str(FRONTEND_DIR / 'assets'), filename)

@app.route('/favicon.ico')
def favicon():
    """站点 favicon（frontend/dist/favicon.ico）。"""
    return send_from_directory(str(FRONTEND_DIR), 'favicon.ico')

@app.route('/vite.svg')
def vite_svg():
    """Vite 默认 logo（frontend/dist/vite.svg）。"""
    return send_from_directory(str(FRONTEND_DIR), 'vite.svg')

@app.route('/changelog/<path:filename>')
def serve_changelog(filename):
    """更新日志静态文件（changelog/ 目录，打包目录缺失时回退 BASE_DIR）。"""
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
    """健康检查/诊断：数据目录、DB 存在性、Python 环境、user_info 计数。"""
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

    # DB 完整 schema 已在模块导入期初始化（init_database + migrate_database，幂等），
    # 此处仅做启动期验证与后台任务装配。
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
    from services.startup import maybe_start_account_check, start_duration_repair

    start_duration_repair()

    # 账号登录状态检查机制:如果设置为「启动时检测」,后台异步检测所有账号 cookie
    maybe_start_account_check(_get_db_path)

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
