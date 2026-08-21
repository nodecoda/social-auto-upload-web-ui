"""抖音 publish_video 编排层契约测试（T15）。

publish_video 是高层编排：参数解析 → 话题≤5 前置校验 → 策略选择 →
parse_schedule_time 排期 → 文件×账号遍历调度 → _upload_one_video。
_upload_one_video 是 220+ 行 DOM 交互,本批 mock 掉,只测编排契约 +
浏览器打开失败冒泡。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from impl.douyin.platform import (
    DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
    DOUYIN_PUBLISH_STRATEGY_SCHEDULED,
    DouyinPlatform,
)

COOKIES_DIR = "cookiesFile"


def _make_platform():
    return DouyinPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_one_video / 排期 / 账号名 运行 publish_video,返回 (result, upload_calls)。"""
    upload = AsyncMock()
    pst = MagicMock(return_value=[datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))])
    with patch.object(platform, '_upload_one_video', upload), \
         patch('impl.douyin.platform.parse_schedule_time', pst), \
         patch('impl.douyin.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.douyin.platform.bind_account_name', MagicMock()):
        result = _run_async(platform.publish_video(**kwargs))
    return result, upload, pst


def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


def _base_kwargs(**overrides):
    kwargs = {
        'title': '测试视频',
        'files': ['/data/v1.mp4'],
        'tags': [],
        'account_file': ['cookie1.json'],
    }
    kwargs.update(overrides)
    return kwargs


# ── 前置校验:话题总数 ≤ 5 ─────────────────────────────────────────────────

class TestPublishValidation:
    def test_desc_hashtags_over(self):
        p = _make_platform()
        with pytest.raises(ValueError, match='超过 5 个'):
            _run_async(p.publish_video(**_base_kwargs(desc='#a #b #c #d #e #f')))

    def test_tags_over(self):
        p = _make_platform()
        with pytest.raises(ValueError, match='超过 5 个'):
            _run_async(p.publish_video(**_base_kwargs(tags=[f't{i}' for i in range(6)])))

    def test_activities_over(self):
        p = _make_platform()
        with pytest.raises(ValueError, match='超过 5 个'):
            _run_async(p.publish_video(**_base_kwargs(activities=['a'] * 6)))

    def test_combined_over(self):
        p = _make_platform()
        with pytest.raises(ValueError):
            _run_async(p.publish_video(**_base_kwargs(desc='#x', tags=['t1', 't2'], activities=['a1', 'a2', 'a3'])))


# ── 发布策略 ───────────────────────────────────────────────────────────────

class TestPublishStrategy:
    def test_immediate_default(self):
        p = _make_platform()
        result, upload, _ = _run_publish(p, **_base_kwargs())
        assert result is True
        assert upload.call_count == 1
        assert upload.await_args.kwargs['publish_strategy'] == DOUYIN_PUBLISH_STRATEGY_IMMEDIATE

    def test_scheduled_with_time(self):
        p = _make_platform()
        result, upload, pst = _run_publish(
            p, **_base_kwargs(enableTimer=True, schedule_time_str='2026-08-21 18:00:00'))
        assert result is True
        pst.assert_called_once()
        assert upload.await_args.kwargs['publish_strategy'] == DOUYIN_PUBLISH_STRATEGY_SCHEDULED
        assert upload.await_args.kwargs['publish_date'] == datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))

    def test_enable_timer_without_time_is_immediate(self):
        p = _make_platform()
        _, upload, _ = _run_publish(p, **_base_kwargs(enableTimer=True))
        assert upload.await_args.kwargs['publish_strategy'] == DOUYIN_PUBLISH_STRATEGY_IMMEDIATE


# ── 遍历调度:文件 × 账号 ───────────────────────────────────────────────────

class TestFanOut:
    def test_multiple_files_multiple_accounts(self):
        p = _make_platform()
        pst = MagicMock(return_value=[datetime(2026, 8, 21, 9, 0, tzinfo=ZoneInfo('Asia/Shanghai')), datetime(2026, 8, 22, 9, 0, tzinfo=ZoneInfo('Asia/Shanghai'))])
        upload = AsyncMock()
        with patch.object(p, '_upload_one_video', upload), \
             patch('impl.douyin.platform.parse_schedule_time', pst), \
             patch('impl.douyin.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.douyin.platform.bind_account_name', MagicMock()):
            result = _run_async(p.publish_video(title='T', files=['/data/v1.mp4', '/data/v2.mp4'], tags=[], account_file=['c1.json', 'c2.json']))
        assert result is True
        assert upload.call_count == 4  # 2 文件 × 2 账号
        # 每个文件的 publish_date 取自对应索引
        for i, call in enumerate(upload.await_args_list):
            # 文件外层循环 × 账号内层循环: 同文件的两次调用共享同一 publish_date
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]
            assert call.kwargs['file_path'] == f'/data/v{i // 2 + 1}.mp4'

    def test_no_accounts_returns_true(self):
        p = _make_platform()
        upload = AsyncMock()
        with patch.object(p, '_upload_one_video', upload), \
             patch('impl.douyin.platform.parse_schedule_time'), \
             patch('impl.douyin.platform.get_account_name_by_cookie_file', return_value=''), \
             patch('impl.douyin.platform.bind_account_name', MagicMock()):
            result = _run_async(p.publish_video(**_base_kwargs(account_file=[])))
        assert result is True
        upload.assert_not_called()


# ── 参数透传 ───────────────────────────────────────────────────────────────

class TestParamPassthrough:
    def test_full_params(self):
        p = _make_platform()
        _, upload, _ = _run_publish(p, **_base_kwargs(
            desc='简介',
            thumbnail_landscape_path='/cov/l.jpg',
            thumbnail_portrait_path='/cov/p.jpg',
            productLink='https://item.com/1',
            productTitle='商品',
            ai_content='AI生成',
            hotspot='热点词',
            tag_type='location',
            tag_value='北京',
            mini_link='https://m',
            mix_id='mix1',
        ))
        call = upload.await_args.kwargs
        assert call['thumbnail_landscape_path'] == '/cov/l.jpg'
        assert call['thumbnail_portrait_path'] == '/cov/p.jpg'
        assert call['product_link'] == 'https://item.com/1'
        assert call['product_title'] == '商品'
        assert call['ai_content'] == 'AI生成'
        assert call['hotspot'] == '热点词'
        assert call['tag_type'] == 'location'
        assert call['tag_value'] == '北京'
        assert call['mini_link'] == 'https://m'
        assert call['mix_id'] == 'mix1'
        assert call['desc'] == '简介'

    def test_activities_forwarded(self):
        p = _make_platform()
        _, upload, _ = _run_publish(p, **_base_kwargs(activities=['官方活动']))
        assert upload.await_args.kwargs['activities'] == ['官方活动']

    def test_cookie_path_resolved(self):
        p = _make_platform()
        _, upload, _ = _run_publish(p, **_base_kwargs(account_file=['ck.json']))
        assert str(Path('ck.json')) in upload.await_args.kwargs['account_file']


# ── _upload_one_video 外层异常 ─────────────────────────────────────────────

class TestUploadOneVideoOuter:
    def test_browser_creation_failure_propagates(self):
        """create_browser 失败不吞异常,冒泡给路由层兜底。"""
        p = _make_platform()
        with patch.object(p, 'create_browser', side_effect=RuntimeError('browser launch failed')), \
             pytest.raises(RuntimeError, match='browser launch failed'):
            _run_async(p._upload_one_video(
                    title='T', file_path='/data/v.mp4', tags=[], publish_date=0,
                    account_file='/cookies/c.json',
                    publish_strategy=DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
                ))
