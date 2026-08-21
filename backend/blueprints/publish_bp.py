"""视频发布 Blueprint：postVideo / postVideo/status / postVideoBatch + 发布域 helper。

从 app.py 单体迁移（域重构），行为与迁移前一致。
注意：_before_publish/_after_publish 钩子仍在 app.py（g.publish_detail_id 机制），
发布历史写入共用 services/publish_history.py。
"""
import asyncio
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Blueprint, g, jsonify, request

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.registry import get_platform
from services import publish_executor as _publish_exec
from services.publish_history import _update_publish_result
from util._logger import get_channel_logger

logger = get_channel_logger("publish")

publish_bp = Blueprint('publish', __name__)

DB_PATH = BASE_DIR / "db" / "database.db"

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


@publish_bp.route('/postVideo', methods=['POST'])
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


@publish_bp.route('/postVideo/status/<task_id>', methods=['GET'])
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


@publish_bp.route('/postVideoBatch', methods=['POST'])
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

