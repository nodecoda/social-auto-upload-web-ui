"""头像代理 Blueprint：绕过 sinaimg.cn 防盗链，后端带 Referer=weibo.com 拉图。

从 app.py 单体迁移（域重构），行为与迁移前一致。
"""
import sys
from pathlib import Path

from flask import Blueprint, Response, jsonify, request

sys.path.insert(0, str(Path(__file__).parent.parent))
from util._logger import get_channel_logger

logger = get_channel_logger("image-proxy")

image_proxy_bp = Blueprint('image_proxy', __name__)


@image_proxy_bp.route('/api/image-proxy')
def image_proxy():
    """头像代理：绕过 sinaimg.cn 防盗链。后端请求带 Referer=weibo.com。"""
    url = request.args.get('url')
    if not url:
        return jsonify({"code": 400, "msg": "缺少 url 参数"}), 400
    import httpx
    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/135.0.0.0 Safari/537.36",
                "Referer": "https://weibo.com/",
            },
            timeout=15,
        )
        return Response(resp.content, mimetype=resp.headers.get("content-type", "image/jpeg"))
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
        logger.warning(f"[image-proxy] fetch failed: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500
