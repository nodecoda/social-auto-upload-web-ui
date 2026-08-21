"""反馈系统代理 Blueprint：HMAC 签名由后端完成，前端永不接触 app_secret。

从 app.py 单体迁移（域重构），行为与迁移前一致。
"""
import hashlib
import hmac
import sys
import time
from pathlib import Path

import requests as _requests
from flask import Blueprint, jsonify, request

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import (
    FEEDBACK_API_BASE_URL,
    FEEDBACK_API_TIMEOUT,
    FEEDBACK_APP_KEY,
    FEEDBACK_APP_SECRET,
)
from impl.settings import read_settings

feedback_bp = Blueprint('feedback', __name__)


def _feedback_configured() -> bool:
    """反馈凭据是否已配置（环境变量 FEEDBACK_APP_KEY / FEEDBACK_APP_SECRET）。"""
    return bool(FEEDBACK_APP_KEY and FEEDBACK_APP_SECRET)


def _feedback_sign(timestamp_ms: str, app_key: str = None, app_secret: str = None) -> str:
    if app_key is None:
        app_key = FEEDBACK_APP_KEY
    if app_secret is None:
        app_secret = FEEDBACK_APP_SECRET
    msg = f"{app_key}{timestamp_ms}{app_secret}".encode()
    return hmac.new(app_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()


def _feedback_headers() -> dict:
    """生成带 HMAC 签名的反馈系统请求头。"""
    ts = str(int(time.time() * 1000))
    return {
        'X-App-Key': FEEDBACK_APP_KEY,
        'X-Timestamp': ts,
        'X-Sign': _feedback_sign(ts),
    }


def _get_feedback_email() -> str:
    """从 settings 表读 feedbackEmail（用户全局邮箱）。空字符串表示未配置。"""
    val = read_settings().get('feedbackEmail')
    return (val or '').strip() if isinstance(val, str) else ''


@feedback_bp.route('/api/feedback/list', methods=['GET'])
def feedback_list():
    """状态筛选：全部 / 待确认 / 处理中 / 已完成 / 已拒绝
    - 不传 status + 不传 include_all → 仅 status 1+2（默认）
    - status=1/2/3/4 → 仅对应状态
    - include_all=true → 全部
    """
    if not _feedback_configured():
        return jsonify({'code': 503, 'message': '反馈系统未配置（缺少 FEEDBACK_APP_KEY / FEEDBACK_APP_SECRET）', 'data': None}), 503
    try:
        page = int(request.args.get('page', 1))
        page_size = min(int(request.args.get('page_size', 20)), 100)
    except ValueError:
        return jsonify({'code': 400, 'message': 'page / page_size 必须是整数', 'data': None}), 400

    status_str = request.args.get('status', '').strip()
    include_all = request.args.get('include_all', '').lower() == 'true'

    params = {'page': page, 'page_size': page_size}
    if status_str:
        try:
            params['status'] = int(status_str)
        except ValueError:
            return jsonify({'code': 400, 'message': 'status 必须是整数 (1-4)', 'data': None}), 400
    elif include_all:
        params['include_all'] = 'true'

    # 从 settings 表读用户邮箱，作为 metoo 计算依据
    viewer_email = _get_feedback_email()
    if viewer_email:
        params['email'] = viewer_email

    try:
        r = _requests.get(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback",
            params=params,
            headers=_feedback_headers(),
            timeout=FEEDBACK_API_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502

    # attachment.file_url 从相对路径改写为绝对 URL
    for item in data.get('data', {}).get('list', []):
        for att in item.get('attachments') or []:
            if att.get('file_url', '').startswith('/'):
                att['file_url'] = FEEDBACK_API_BASE_URL + att['file_url']

    return jsonify(data)


@feedback_bp.route('/api/feedback/submit', methods=['POST'])
def feedback_submit():
    if not _feedback_configured():
        return jsonify({'code': 503, 'message': '反馈系统未配置（缺少 FEEDBACK_APP_KEY / FEEDBACK_APP_SECRET）', 'data': None}), 503
    content = request.form.get('content', '').strip()
    # 邮箱优先取表单（覆盖场景），否则从 settings 读
    email = request.form.get('email', '').strip() or _get_feedback_email()
    if not email or not content:
        return jsonify({'code': 400, 'message': '邮箱和内容必填；如未配置邮箱请先在设置页填写', 'data': None}), 400

    files = []
    for f in request.files.getlist('files'):
        files.append(('files', (f.filename, f.stream, f.mimetype)))

    try:
        r = _requests.post(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback",
            data={'email': email, 'content': content},
            files=files,
            headers=_feedback_headers(),
            timeout=FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502


@feedback_bp.route('/api/feedback/vote', methods=['POST'])
def feedback_vote():
    if not _feedback_configured():
        return jsonify({'code': 503, 'message': '反馈系统未配置（缺少 FEEDBACK_APP_KEY / FEEDBACK_APP_SECRET）', 'data': None}), 503
    body = request.get_json(silent=True) or {}
    fb_id = body.get('id')
    # 邮箱优先取 body（允许前端临时用别的身份），否则从 settings 读
    email = (body.get('email') or '').strip() or _get_feedback_email()
    if not fb_id or not email:
        return jsonify({'code': 400, 'message': 'id 和 email 必填；如未配置邮箱请先在设置页填写', 'data': None}), 400

    try:
        r = _requests.post(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback/{fb_id}/vote",
            json={'email': email},
            headers=_feedback_headers(),
            timeout=FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502
