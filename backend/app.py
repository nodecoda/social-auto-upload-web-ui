import asyncio
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
from impl.registry import get_platform
from services import publish_executor as _publish_exec

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

app.register_blueprint(account_bp)
app.register_blueprint(feedback_bp)
app.register_blueprint(image_proxy_bp)
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

def _resolve_material_path(path_or_stored_path):
    """兼容旧调用：转发到 storage.resolve_material_path"""
    from storage import resolve_material_path
    return resolve_material_path(path_or_stored_path)

def _resolve_video_format_from_db(file_list_raw):
    """根据发布视频的 stored_path 查素材表 orientation,映射成 video_format。

    素材表 materials.orientation: 'horizontal' / 'vertical' / 'square' / ''
    映射:horizontal → landscape,vertical/square → portrait,空 → ''
    (square 归竖版,因多数竖屏平台优先)

    file_list_raw: 前端原始 fileList(stored_path 相对路径列表),取第一个。
    返回 ('landscape' | 'portrait' | '')
    """
    if not file_list_raw:
        return ''
    first = file_list_raw[0]
    if not isinstance(first, str) or not first:
        return ''
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT orientation FROM materials WHERE stored_path = ?",
            (first,),
        ).fetchone()
        conn.close()
        orientation = (row[0] if row else '') or ''
        if orientation == 'horizontal':
            return 'landscape'
        elif orientation in ('vertical', 'square'):
            return 'portrait'
        return ''
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"查询素材 orientation 失败(降级忽略): {e}")
        return ''


def _validate_publish_video(type_id, file_list):
    """校验视频文件是否符合平台限制。

    Returns:
        (ok, error_msg). 通过时 error_msg 为空字符串。
        材料缺失时跳过校验（兼容老路径直接上传）。
    """
    from util.video_limits import validate_video_for_platform

    if not file_list:
        return True, ""

    platform = get_platform(type_id)
    if platform is None or not hasattr(platform, "platform_key"):
        return True, ""

    platform_key = platform.platform_key

    first_file = next((f for f in file_list if f), None)
    if not first_file:
        return True, ""

    # 兜底：存量视频 duration 可能为 0（草稿/历史恢复绕过了素材库 probe）。
    # 在读 DB 拿到 duration 后，若仍 <=0 则同步补全，确保校验拿到真实时长。
    # 与原查询合并为一次 DB 访问，避免重复连接；表缺失/异常一律降级跳过。
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT duration, file_size FROM materials WHERE stored_path = ?",
            (first_file,),
        ).fetchone()

        # 时长缺失则同步兜底补全，再重读一次拿到最新值
        if row and (not row["duration"] or row["duration"] <= 0):
            conn.close()
            try:
                from services.duration_repair import ensure_duration_or_probe
                ensure_duration_or_probe(first_file, row["duration"])
            except Exception as _e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.debug("提交前时长兜底失败（不影响后续校验）: %s", str(_e))
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT duration, file_size FROM materials WHERE stored_path = ?",
                (first_file,),
            ).fetchone()
        conn.close()
    except Exception:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
        return True, ""

    if row is None:
        return True, ""

    return validate_video_for_platform(platform_key, row["duration"], row["file_size"])

def _enqueue_publish(platform, publish_kwargs, detail_id):
    """把发布任务丢进后台串行执行器，立即返回 task_id。

    发布（浏览器自动化）在 publish_executor 的单工作线程里执行：
    - 任意时刻最多 1 个发布在跑，从根上杜绝并发开多个浏览器；
    - HTTP 请求立即返回，前端轮询 /postVideo/status/<task_id> 拿结果，
      大文件上传再久也不会出现「接口超时但后端还在发」。
    发布结束后由 job 更新 publish_details / publish_batches。
    """
    publish_fn = platform.publish_video

    def _job(task_id):
        _publish_exec.mark_running(task_id)
        try:
            if asyncio.iscoroutinefunction(publish_fn):
                result = asyncio.run(publish_fn(**publish_kwargs))
            else:
                result = publish_fn(**publish_kwargs)
            now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat()
            if result:
                # 先落库再更新任务状态：前端轮询到终态时，发布历史一定已写入
                if detail_id:
                    _update_publish_result(detail_id, 'success', now)
                _publish_exec.mark_finished(task_id, 'success', '发布成功')
            else:
                _finish_publish_failed(
                    task_id, detail_id, '发布失败：页面未跳转，表单校验未通过')
        except asyncio.CancelledError:
            # 用户手动关闭了浏览器 → _browser 的 watchdog cancel 了发布 task
            logger.info("发布视频被取消：用户关闭了浏览器")
            _finish_publish_failed(task_id, detail_id, '用户关闭了浏览器，发布已取消')
        except Exception as e:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
            err_msg = str(e)
            # 浏览器被用户关闭时, Playwright 操作会抛 "Target page, context or
            # browser has been closed" / "Browser has been closed" 等。watchdog
            # 0.5s 轮询可能慢于异常抛出, 此时异常先冒泡到这里, 转成友好提示。
            if "has been closed" in err_msg or "Target page" in err_msg:
                logger.info("发布视频被取消：用户关闭了浏览器")
                msg = '用户关闭了浏览器，发布已取消'
            else:
                logger.info(f"发布视频时出错: {err_msg}")
                msg = f'发布失败: {err_msg}'
            _finish_publish_failed(task_id, detail_id, msg)

    return _publish_exec.submit(_job)

def _finish_publish_failed(task_id, detail_id, msg):
    """发布 job 失败收尾：更新任务状态 + 发布历史明细（先落库再标记终态）。"""
    if detail_id:
        _update_publish_result(detail_id, 'failed', datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat(), msg)
    _publish_exec.mark_finished(task_id, 'failed', msg)

@app.route('/postVideo', methods=['POST'])
def postVideo():
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空", "data": None}), 400

    logger.info("postVideo data: tag_type=%s, tag_value=%s, hotspot=%s, mix_id=%s",
                 data.get('tag_type'), data.get('tag_value'), data.get('hotspot'), data.get('mix_id'))
    # 诊断: B 站(platform_id=5) 请求体是否含转载来源
    logger.info("[postVideo DIAG] type=%s, biliRepostSource=%r, creationDeclaration=%r",
                data.get('type'), data.get('biliRepostSource'), data.get('creationDeclaration'))

    platform = get_platform(data.get('type'))
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    # 视频时长/大小校验（早于 publish_video，避免无效提交）
    ok, err = _validate_publish_video(data.get('type'), data.get('fileList', []))
    if not ok:
        logger.info(f"发布视频校验失败: {err}")
        return jsonify({"code": 400, "msg": err}), 400

    # 标题长度校验（如小红书 ≤ 20 字，B 站 ≤ 80 字，emoji 按 3 算）
    from util.video_limits import validate_desc_for_platform, validate_title_for_platform
    ok, err = validate_title_for_platform(platform.platform_key, data.get('title', '') or '')
    if not ok:
        logger.info(f"发布标题校验失败: {err}")
        return jsonify({"code": 400, "msg": err}), 400

    # 简介长度校验（如 B 站 ≤ 2000 字，emoji 按 3 算）
    ok, err = validate_desc_for_platform(platform.platform_key, data.get('description', '') or '')
    if not ok:
        logger.info(f"发布简介校验失败: {err}")
        return jsonify({"code": 400, "msg": err}), 400

    try:
        # Resolve file paths through storage abstraction
        file_list = [_resolve_material_path(f) for f in data.get('fileList', [])]
        thumbnail_landscape = _resolve_material_path(data.get('thumbnailLandscape', ''))
        thumbnail_portrait = _resolve_material_path(data.get('thumbnailPortrait', ''))
        # 16:9 / 9:16 次尺寸封面(知乎等平台横版视频用 16:9)
        thumbnail_landscape_169 = _resolve_material_path(data.get('thumbnailLandscape169', ''))
        thumbnail_portrait_916 = _resolve_material_path(data.get('thumbnailPortrait916', ''))

        # 兜底：只上传了横版或竖版之一时，另一个用同图（保证 2 个封面都有内容）
        if thumbnail_landscape and not thumbnail_portrait:
            thumbnail_portrait = thumbnail_landscape
        elif thumbnail_portrait and not thumbnail_landscape:
            thumbnail_landscape = thumbnail_portrait

        # 根据素材表 orientation 推导 video_format(横/竖),覆盖前端字段。
        # 支付宝等平台据此选对应方向封面;前端 videoFormat/videoOrientation 不可信(已移除选择)。
        db_video_format = _resolve_video_format_from_db(data.get('fileList', []))
        if db_video_format:
            data['videoFormat'] = db_video_format
            data['videoOrientation'] = 'horizontal' if db_video_format == 'landscape' else 'vertical'
            logger.info(f"[发布] 素材表 orientation 推导 video_format={db_video_format}")

        # 发布参数统一构建一份：协程/同步平台吃同一组 kwargs，
        # 实际调用方式（asyncio.run / 直接调）由后台执行线程决定。
        activities = data.get('activities', [])
        hotspot = data.get('hotspot', '')
        tag_type = data.get('tag_type', '')
        tag_value = data.get('tag_value', '')
        mini_link = data.get('mini_link', '')
        mix_id = data.get('mix_id', '')

        publish_kwargs = dict(
                title=data.get('title'),
                files=file_list,
                tags=data.get('tags'),
                activities=activities,
                account_file=data.get('accountList', []),
                category=data.get('category'),
                enableTimer=data.get('enableTimer'),
                videos_per_day=data.get('videosPerDay'),
                daily_times=data.get('dailyTimes'),
                start_days=data.get('startDays'),
                thumbnail_path=data.get('thumbnail', ''),
                thumbnail_landscape_path=thumbnail_landscape,
                thumbnail_portrait_path=thumbnail_portrait,
                # 16:9 / 9:16 次尺寸封面(知乎横版视频用 16:9)
                thumbnail_landscape_169_path=thumbnail_landscape_169,
                thumbnail_portrait_916_path=thumbnail_portrait_916,
                productLink=data.get('productLink', ''),
                productTitle=data.get('productTitle', ''),
                desc=data.get('description', ''),
                schedule_time_str=data.get('scheduleTime', ''),
                ai_content=data.get('aiContent', ''),
                creation_declaration=data.get('creationDeclaration', ''),
                # B 站转载来源(创作声明=转载 时必填)
                bili_repost_source=data.get('biliRepostSource', ''),
                risk_warning=data.get('riskWarning', ''),
                enable_cash_activity=data.get('enableCashActivity', False),
                supplementary_declaration=data.get('supplementaryDeclaration', ''),
                is_draft=data.get('isDraft', False),
                audience=data.get('audience', 'not_kids'),
                altered_content=data.get('alteredContent', False),
                hotspot=hotspot,
                tag_type=tag_type,
                tag_value=tag_value,
                mini_link=mini_link,
                mix_id=mix_id,
                content_statement=data.get('contentStatement', ''),
                content_statement2=data.get('contentStatement2', ''),
                content_statement2_optional=data.get('contentStatement2Optional', ''),
                weibo_collection=data.get('weiboCollection', ''),
                author_statement=data.get('authorStatement', ''),
                compilation=data.get('compilation', ''),
                video_format=data.get('videoFormat', ''),
                # 支付宝转载来源(作者声明=内容为转载 时必填)
                reprint_url=data.get('reprintUrl', ''),
                # 今日头条特有参数
                enable_generate_image=data.get('enableGenerateImage', True),
                collection_id=data.get('collection', ''),
                extend_link=data.get('extendLink', False),
                extend_link_url=data.get('extendLinkUrl', ''),
                # 视频素材方向(horizontal/vertical/square),小红书据此选封面
                video_orientation=data.get('videoOrientation', ''),
                # 小红书合集(账号级配置,用 xhs_ 前缀避免与头条 collection_id 冲突)
                xhs_collection_id=data.get('collectionId', ''),
                xhs_collection_name=data.get('collectionName', ''),
                # 小红书内容来源声明(平台级):自主拍摄/来源转载
                xhs_source_type=data.get('xhsSourceType', ''),
                xhs_shoot_location=data.get('xhsShootLocation', ''),
                xhs_shoot_date=data.get('xhsShootDate', ''),
                xhs_repost_source=data.get('xhsRepostSource', ''),
                # B 站合集(账号级)
                bili_collection_name=data.get('biliCollectionName', ''),
                # 视频号合集(账号级)
                channels_collection_name=data.get('channelsCollectionName', ''),
                # 视频号位置(平台级,空=不显示位置)
                channels_location_name=data.get('channelsLocationName', ''),
                # 视频号活动(平台级,空=不参与活动)
                channels_activity_name=data.get('channelsActivityName', ''),
                # 视频号活动复合 id: name|creator_name,用于同名不同发起人的精确匹配
                channels_activity_id=(data.get('channelsActivityData') or {}).get('activity_id', ''),
                # 视频号视频标注(平台级):所有选项(含「无需标注」)都会去页面下拉真正选中
                channels_mark_tag=data.get('channelsMarkTag', '无需标注'),
                channels_shoot_date=data.get('channelsShootDate', ''),
                channels_shoot_region=data.get('channelsShootRegion', []),
                channels_repost_source=data.get('channelsRepostSource', ''),
                # CSDN 是否推荐
                recommend=data.get('recommend', False),
                # VIVO 平台特有参数
                vivo_location_name=data.get('vivoLocationName', ''),
                vivo_distribution=data.get('vivoDistribution', False),
                vivo_declaration=data.get('vivoDeclaration', ''),
                vivo_privacy=data.get('vivoPrivacy', '公开'),
                vivo_download_permission=data.get('vivoDownloadPermission', '允许'),
                # 微信公众号特有参数
                is_original=data.get('isOriginal', False),
                gzh_collection_name=data.get('gzhCollectionName', ''),
                gzh_claim_source=data.get('gzhClaimSource', ''),
                # 淘宝光合创作者声明
                guanghe_claim=data.get('guangheClaim', ''),
                # 淘宝光合关联商品/店铺(发布时按名称在光合面板内搜索匹配勾选)
                guangheLinkType=data.get('guangheLinkType', ''),
                guangheProducts=data.get('guangheProducts') or data.get('guangheProductNames') or [],
                guangheShops=data.get('guangheShops') or data.get('guangheShopNames') or [],
                # 京东平台特有参数
                jd_related_type=data.get('jdRelatedType', ''),
                jd_products=data.get('jdProducts') or data.get('jdProductNames') or [],
                jd_novel=data.get('jdNovel', ''),
                jd_declaration=data.get('jdDeclaration', ''),
                schedule_time=data.get('scheduleTime', ''),
        )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"发布视频时出错: {e!s}")
        return jsonify({"code": 500, "msg": f"发布失败: {e!s}", "data": None}), 500

    # 异步发布：入队后台串行执行器，立即返回 taskId。根治「大视频上传
    # 期间 HTTP 长连接被传输层掐断 → 前端判失败继续发下一账号 → 多个
    # 浏览器并发发布」的问题（详见 services/publish_executor.py）。
    detail_id = getattr(g, 'publish_detail_id', None)
    task_id = _enqueue_publish(platform, publish_kwargs, detail_id)
    return jsonify({"code": 200, "msg": "发布任务已提交", "data": {"taskId": task_id}}), 200

@app.route('/postVideo/status/<task_id>', methods=['GET'])
def postVideo_status(task_id):
    """查询异步发布任务状态（前端在发布期间轮询本接口）。

    data.status: queued | running | success | failed。
    404 = 任务不存在（后端重启导致内存态丢失），结果以发布历史为准。
    """
    task = _publish_exec.get(task_id)
    if task is None:
        return jsonify({
            "code": 404,
            "msg": "任务不存在或已过期（后端可能已重启），请在发布历史中确认结果",
            "data": None,
        }), 404
    return jsonify({"code": 200, "data": task}), 200

@app.route('/postVideoBatch', methods=['POST'])
def postVideoBatch():
    data_list = request.get_json()
    if not isinstance(data_list, list):
        return jsonify({"code": 400, "msg": "Expected a JSON array", "data": None}), 400

    failures = []
    for idx, data in enumerate(data_list):
        platform = get_platform(data.get('type'))
        if not platform:
            failures.append({"index": idx, "reason": "不支持的平台类型"})
            continue

        # 视频时长/大小校验
        ok, err = _validate_publish_video(data.get('type'), data.get('fileList', []))
        if not ok:
            failures.append({"index": idx, "reason": err})
            continue

        try:
            # Resolve file paths through storage abstraction
            file_list = [_resolve_material_path(f) for f in data.get('fileList', [])]
            thumbnail_landscape = _resolve_material_path(data.get('thumbnailLandscape', ''))
            thumbnail_portrait = _resolve_material_path(data.get('thumbnailPortrait', ''))

            # 根据素材表 orientation 推导 video_format(横/竖),覆盖前端字段
            db_video_format = _resolve_video_format_from_db(data.get('fileList', []))
            if db_video_format:
                data['videoFormat'] = db_video_format
                data['videoOrientation'] = 'horizontal' if db_video_format == 'landscape' else 'vertical'
                logger.info(f"[发布] 素材表 orientation 推导 video_format={db_video_format}")

            publish_fn = platform.publish_video
            if asyncio.iscoroutinefunction(publish_fn):
                result = asyncio.run(publish_fn(
                    title=data.get('title'),
                    files=file_list,
                    tags=data.get('tags'),
                    account_file=data.get('accountList', []),
                    category=data.get('category'),
                    enableTimer=data.get('enableTimer'),
                    videos_per_day=data.get('videosPerDay'),
                    daily_times=data.get('dailyTimes'),
                    start_days=data.get('startDays'),
                    thumbnail_path=data.get('thumbnail', ''),
                    thumbnail_landscape_path=thumbnail_landscape,
                    thumbnail_portrait_path=thumbnail_portrait,
                    productLink=data.get('productLink', ''),
                    productTitle=data.get('productTitle', ''),
                    desc=data.get('description', ''),
                    schedule_time_str=data.get('scheduleTime', ''),
                    ai_content=data.get('aiContent', ''),
                    creation_declaration=data.get('creationDeclaration', ''),
                # B 站转载来源(创作声明=转载 时必填)
                bili_repost_source=data.get('biliRepostSource', ''),
                    risk_warning=data.get('riskWarning', ''),
                    enable_cash_activity=data.get('enableCashActivity', False),
                    supplementary_declaration=data.get('supplementaryDeclaration', ''),
                    is_draft=data.get('isDraft', False),
                    audience=data.get('audience', 'not_kids'),
                    altered_content=data.get('alteredContent', False),
                    # 微信公众号特有参数
                    is_original=data.get('isOriginal', False),
                    gzh_collection_name=data.get('gzhCollectionName', ''),
                    gzh_claim_source=data.get('gzhClaimSource', ''),
                # 淘宝光合创作者声明
                guanghe_claim=data.get('guangheClaim', ''),
                # 淘宝光合关联商品/店铺(发布时按名称在光合面板内搜索匹配勾选)
                guangheLinkType=data.get('guangheLinkType', ''),
                guangheProducts=data.get('guangheProducts') or data.get('guangheProductNames') or [],
                guangheShops=data.get('guangheShops') or data.get('guangheShopNames') or [],
                # 京东平台特有参数
                jd_related_type=data.get('jdRelatedType', ''),
                jd_products=data.get('jdProducts') or data.get('jdProductNames') or [],
                jd_novel=data.get('jdNovel', ''),
                jd_declaration=data.get('jdDeclaration', ''),
                schedule_time=data.get('scheduleTime', ''),
                ))
            else:
                result = publish_fn(
                    title=data.get('title'),
                    files=file_list,
                    tags=data.get('tags'),
                    account_file=data.get('accountList', []),
                    category=data.get('category'),
                    enableTimer=data.get('enableTimer'),
                    videos_per_day=data.get('videosPerDay'),
                    daily_times=data.get('dailyTimes'),
                    start_days=data.get('startDays'),
                    thumbnail_path=data.get('thumbnail', ''),
                    thumbnail_landscape_path=thumbnail_landscape,
                    thumbnail_portrait_path=thumbnail_portrait,
                    productLink=data.get('productLink', ''),
                    productTitle=data.get('productTitle', ''),
                    desc=data.get('description', ''),
                    schedule_time_str=data.get('scheduleTime', ''),
                    ai_content=data.get('aiContent', ''),
                    creation_declaration=data.get('creationDeclaration', ''),
                # B 站转载来源(创作声明=转载 时必填)
                bili_repost_source=data.get('biliRepostSource', ''),
                    risk_warning=data.get('riskWarning', ''),
                    enable_cash_activity=data.get('enableCashActivity', False),
                    supplementary_declaration=data.get('supplementaryDeclaration', ''),
                    is_draft=data.get('isDraft', False),
                    audience=data.get('audience', 'not_kids'),
                    altered_content=data.get('alteredContent', False),
                    # 微信公众号特有参数
                    is_original=data.get('isOriginal', False),
                    gzh_collection_name=data.get('gzhCollectionName', ''),
                    gzh_claim_source=data.get('gzhClaimSource', ''),
                # 淘宝光合创作者声明
                guanghe_claim=data.get('guangheClaim', ''),
                # 淘宝光合关联商品/店铺(发布时按名称在光合面板内搜索匹配勾选)
                guangheLinkType=data.get('guangheLinkType', ''),
                guangheProducts=data.get('guangheProducts') or data.get('guangheProductNames') or [],
                guangheShops=data.get('guangheShops') or data.get('guangheShopNames') or [],
                # 京东平台特有参数
                jd_related_type=data.get('jdRelatedType', ''),
                jd_products=data.get('jdProducts') or data.get('jdProductNames') or [],
                jd_novel=data.get('jdNovel', ''),
                jd_declaration=data.get('jdDeclaration', ''),
                schedule_time=data.get('scheduleTime', ''),
                )
            if not result:
                failures.append({"index": idx, "reason": "发布失败：页面未跳转"})
        except Exception as e:  # noqa: BLE001 -- 捕获后返回兜底值/错误响应
            failures.append({"index": idx, "reason": str(e)})

    if failures:
        return jsonify({"code": 500, "msg": f"{len(failures)} 个发布失败", "errors": failures}), 500
    return jsonify({"code": 200, "msg": None, "data": None}), 200

# ── Publish history tracking ────────────────────────────────

def _record_publish(batch_id, detail_id, platform, account_name, account_id,
                    video_path, title, description, tags, status, started_at,
                    account_configs, video_material_id='',
                    landscape_cover_material_id='',
                    portrait_cover_material_id=''):
    """插 1 行 publish_batches（如果不存在）+ 1 行 publish_details"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            # batch 用 INSERT OR IGNORE，多次同 batchId 调用只插一次
            conn.execute(
                """INSERT OR IGNORE INTO publish_batches
                   (id, type, title, description, video_material_id,
                    landscape_cover_material_id, portrait_cover_material_id,
                    account_count, status, created_at, updated_at)
                   VALUES (?, 'video', ?, ?, ?, ?, ?, 0, 'pending', ?, ?)""",
                (batch_id, title, description, video_material_id,
                 landscape_cover_material_id, portrait_cover_material_id,
                 started_at, started_at)
            )
            conn.execute(
                """INSERT INTO publish_details
                   (id, batch_id, account_id, account_name, platform, account_configs,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (detail_id, batch_id, account_id, account_name, platform,
                 json.dumps(account_configs, ensure_ascii=False), status, started_at)
            )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[History] 记录发布失败: {e}")

def _update_publish_result(detail_id, status, finished_at, error_message=""):
    """更新 1 行 publish_details + 聚合 publish_batches 状态"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "UPDATE publish_details SET status=?, finished_at=?, error_message=? WHERE id=?",
                (status, finished_at, error_message, detail_id)
            )
            # 拿 batch_id
            row = conn.execute(
                "SELECT batch_id FROM publish_details WHERE id=?", (detail_id,)
            ).fetchone()
            if not row:
                return
            batch_id = row[0]
            # 聚合：算 success/failed 数量，更新 batch 状态
            counts = conn.execute(
                """SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_n,
                    SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_n
                   FROM publish_details WHERE batch_id=?""",
                (batch_id,)
            ).fetchone()
            total, succ, fail = counts[0], counts[1] or 0, counts[2] or 0
            if total == 0:
                batch_status = 'pending'
            elif fail == 0:
                batch_status = 'success'
            elif succ == 0:
                batch_status = 'failed'
            else:
                batch_status = 'partial'
            conn.execute(
                """UPDATE publish_batches
                   SET status=?, success_count=?, failed_count=?, account_count=?,
                       finished_at=?, updated_at=?
                   WHERE id=?""",
                (batch_status, succ, fail, total, finished_at, finished_at, batch_id)
            )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[History] 更新发布结果失败: {e}")

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
            _update_publish_result(g.publish_detail_id, 'failed', now, resp_data.get('msg', '提交失败'))
        else:
            error_msg = ''
            try:
                resp_data = json.loads(response.get_data(as_text=True))
                error_msg = resp_data.get('msg', '')
            except (json.JSONDecodeError, ValueError):
                error_msg = f'HTTP {response.status_code}'
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
