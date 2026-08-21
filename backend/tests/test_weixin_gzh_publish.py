"""微信公众号平台发布契约测试（T15 主批）。

覆盖：
- 纯函数: _extract_token / _build_home_url / _build_publish_datetime /
  _resolve_date_label / _parse_cookie_to_storage_state
- 编排层: publish_video(sync 包装) / _upload_all(文件×账号笛卡尔积+封面优先级)
- evaluate 驱动轮询: _resolve_token / _wait_for_video_uploaded /
  _click_primary_when_enabled / _dismiss_upload_notice
"""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from impl.weixin_gzh.platform import _LOGIN_URL, WeixinGzhPlatform

_REAL_SLEEP = None


class _FakePage:
    """极简 page:url 属性 + goto/evaluate 记录。"""

    def __init__(self, url='', evaluate_results=None):
        self.url = url
        self.evaluate_results = list(evaluate_results or [])
        self.events = []

    async def goto(self, url, **kwargs):
        self.events.append(('goto', url))

    async def evaluate(self, js, *args):
        self.events.append(('evaluate', js[:30]))
        if self.evaluate_results:
            return self.evaluate_results.pop(0)
        return False


def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


# ── 纯函数 ─────────────────────────────────────────────────────────────────

class TestExtractToken:
    def test_home_url_with_token(self):
        page = _FakePage(url='https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=123456')
        assert WeixinGzhPlatform._extract_token(page) == '123456'

    def test_no_token(self):
        page = _FakePage(url='https://mp.weixin.qq.com/')
        assert WeixinGzhPlatform._extract_token(page) == ''

    def test_ampersand_token(self):
        page = _FakePage(url='https://mp.weixin.qq.com/cgi-bin/home?lang=zh_CN&token=888')
        assert WeixinGzhPlatform._extract_token(page) == '888'

    def test_url_property_raises(self):
        class _Bad:
            @property
            def url(self):
                raise RuntimeError('boom')
        assert WeixinGzhPlatform._extract_token(_Bad()) == ''


class TestBuildHomeUrl:
    def test_with_token(self):
        assert WeixinGzhPlatform._build_home_url('123') == (
            'https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=123')

    def test_empty_token_login_url(self):
        assert WeixinGzhPlatform._build_home_url('') == _LOGIN_URL


class TestBuildPublishDatetime:
    def test_parsed(self):
        dt = datetime(2026, 8, 22, 10, 30, tzinfo=ZoneInfo('Asia/Shanghai'))
        with patch('impl.weixin_gzh.platform.parse_schedule_time', return_value=[dt]):
            assert WeixinGzhPlatform._build_publish_datetime('2026-08-22 10:30', 1) == dt

    def test_empty_result_zero(self):
        with patch('impl.weixin_gzh.platform.parse_schedule_time', return_value=[]):
            assert WeixinGzhPlatform._build_publish_datetime('bad', 1) == 0


class TestResolveDateLabel:
    def _today(self):
        return datetime.now(ZoneInfo('Asia/Shanghai'))

    def test_today(self):
        assert WeixinGzhPlatform._resolve_date_label(self._today()) == '今天'

    def test_tomorrow(self):
        assert WeixinGzhPlatform._resolve_date_label(self._today() + timedelta(days=1)) == '明天'

    def test_absolute_date(self):
        assert WeixinGzhPlatform._resolve_date_label(datetime(2026, 8, 30, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))) == '8月30日'


class TestParseCookieToStorageState:
    def test_basic(self):
        p = WeixinGzhPlatform()
        cookies, origins = p._parse_cookie_to_storage_state('a=1; b=2')
        assert origins == []
        assert len(cookies) == 2
        assert cookies[0]['name'] == 'a'
        assert cookies[0]['value'] == '1'
        assert cookies[0]['domain'] == '.qq.com'
        assert cookies[0]['httpOnly'] is True

    def test_expires_future(self):
        p = WeixinGzhPlatform()
        cookies, _ = p._parse_cookie_to_storage_state('a=1')
        assert cookies[0]['expires'] > 1000  # 时间戳远大于 0

    def test_skips_empty_and_malformed(self):
        p = WeixinGzhPlatform()
        cookies, _ = p._parse_cookie_to_storage_state('a=1; ; noequals; b=2')
        assert [c['name'] for c in cookies] == ['a', 'b']

    def test_value_with_equals(self):
        p = WeixinGzhPlatform()
        cookies, _ = p._parse_cookie_to_storage_state('token=a=b=c')
        assert cookies[0]['value'] == 'a=b=c'


# ── 编排层 ─────────────────────────────────────────────────────────────────

class TestPublishVideo:
    def test_sync_wrapper_runs_upload_all(self):
        p = WeixinGzhPlatform()
        with patch.object(p, '_upload_all', AsyncMock()) as m:
            result = asyncio.run(p.publish_video(title='T', files=['/v.mp4'], account_file=['c.json']))
        assert result is True
        m.assert_awaited_once()
        assert m.await_args.kwargs['title'] == 'T'


class TestUploadAll:
    def _run(self, platform, **kwargs):
        upload = AsyncMock()
        with patch.object(platform, '_upload_one_video', upload), \
             patch('impl.weixin_gzh.platform.get_account_name_by_cookie_file', return_value='号'), \
             patch('impl.weixin_gzh.platform.bind_account_name', MagicMock()):
            _run_async(platform._upload_all(**kwargs))
        return upload

    def test_cartesian_files_accounts(self):
        p = WeixinGzhPlatform()
        upload = self._run(p, title='T', files=['/v1.mp4', '/v2.mp4'],
                           account_file=['c1.json', 'c2.json'])
        assert upload.call_count == 4
        # 文件外层循环 × 账号内层循环: v1×2 账号, v2×2 账号
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['file_path'] == f'/v{i // 2 + 1}.mp4'

    def test_cover_priority_169_first(self):
        p = WeixinGzhPlatform()
        upload = self._run(p, title='T', files=['/v.mp4'], account_file=['c.json'],
                           thumbnail_landscape_169_path='/cov/169.jpg',
                           thumbnail_landscape_path='/cov/l.jpg',
                           thumbnail_portrait_path='/cov/p.jpg')
        assert upload.await_args.kwargs['cover_path'] == '/cov/169.jpg'

    def test_cover_landscape_fallback(self):
        p = WeixinGzhPlatform()
        upload = self._run(p, title='T', files=['/v.mp4'], account_file=['c.json'],
                           thumbnail_landscape_path='/cov/l.jpg')
        assert upload.await_args.kwargs['cover_path'] == '/cov/l.jpg'

    def test_cover_none(self):
        p = WeixinGzhPlatform()
        upload = self._run(p, title='T', files=['/v.mp4'], account_file=['c.json'])
        assert upload.await_args.kwargs['cover_path'] is None

    def test_params_passthrough(self):
        p = WeixinGzhPlatform()
        upload = self._run(p, title='标题', files=['/v.mp4'], account_file=['c.json'],
                           tags=['t1'], desc='简介', is_original=True,
                           gzh_collection_name='合集', gzh_claim_source='原创来源',
                           enableTimer=True, schedule_time_str='2026-08-21 12:00')
        kw = upload.await_args.kwargs
        assert kw['title'] == '标题'
        assert kw['tags'] == ['t1']
        assert kw['desc'] == '简介'
        assert kw['is_original'] is True
        assert kw['gzh_collection_name'] == '合集'
        assert kw['gzh_claim_source'] == '原创来源'
        assert kw['enable_timer'] is True
        assert kw['schedule_time_str'] == '2026-08-21 12:00'
        assert kw['files_count'] == 1

    def test_no_accounts_no_calls(self):
        p = WeixinGzhPlatform()
        upload = self._run(p, title='T', files=['/v.mp4'], account_file=[])
        upload.assert_not_called()


# ── evaluate 驱动轮询 ──────────────────────────────────────────────────────

class TestResolveToken:
    def test_success(self):
        page = _FakePage(url='https://mp.weixin.qq.com/cgi-bin/home?token=999')
        with patch('impl.weixin_gzh.platform.asyncio.sleep', AsyncMock()):
            assert _run_async(WeixinGzhPlatform._resolve_token(page)) == '999'
        assert page.events[0][0] == 'goto'

    def test_failure_timeout(self):
        page = _FakePage(url='https://mp.weixin.qq.com/')
        with patch('impl.weixin_gzh.platform.asyncio.sleep', AsyncMock()):
            assert _run_async(WeixinGzhPlatform._resolve_token(page)) == ''
        assert page.events[0] == ('goto', 'https://mp.weixin.qq.com/')


class TestWaitForVideoUploaded:
    def test_success_signal(self):
        page = _FakePage(evaluate_results=[True])
        _run_async(WeixinGzhPlatform._wait_for_video_uploaded(page, timeout_s=30))

    def test_fail_signal_raises(self):
        """evaluate 返回失败信号脚本的结果为 True → RuntimeError。"""
        page = _FakePage(evaluate_results=[False, True])
        with pytest.raises(RuntimeError, match='转码失败'):
            _run_async(WeixinGzhPlatform._wait_for_video_uploaded(page, timeout_s=30))

    def test_timeout_raises(self):
        page = _FakePage(evaluate_results=[False, False])
        with patch('impl.weixin_gzh.platform.asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='等待超时'):
            _run_async(WeixinGzhPlatform._wait_for_video_uploaded(page, timeout_s=1))


class TestClickPrimaryWhenEnabled:
    def test_clicked(self):
        page = _FakePage(evaluate_results=[True])
        _run_async(WeixinGzhPlatform._click_primary_when_enabled(page, '保存', timeout_s=10))

    def test_timeout(self):
        page = _FakePage(evaluate_results=[False])
        with patch('impl.weixin_gzh.platform.asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='保存'):
            _run_async(WeixinGzhPlatform._click_primary_when_enabled(page, '保存', timeout_s=1))


class TestDismissUploadNotice:
    def test_clicked_true(self):
        page = _FakePage(evaluate_results=[True])
        _run_async(WeixinGzhPlatform._dismiss_upload_notice(page))

    def test_not_found(self):
        page = _FakePage(evaluate_results=[False])
        _run_async(WeixinGzhPlatform._dismiss_upload_notice(page))

    def test_evaluate_raises(self):
        page = _FakePage(evaluate_results=[])

        async def _boom(js, *a):
            raise RuntimeError('evaluate failed')
        page.evaluate = _boom
        _run_async(WeixinGzhPlatform._dismiss_upload_notice(page))  # 非致命,不抛
