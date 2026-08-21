"""小红书 publish_video 编排层契约测试（T19）。

publish_video(同步) 是小红书特有结构: 话题总数≤10 前置校验(描述 #xxx+标签) →
方向感知封面选择(竖版优先平台) → XHS compat 排期(无定时→0) →
同步循环内 asyncio.run(_publish_single_video 模块级函数)。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.xiaohongshu.platform import XiaohongshuPlatform


def _make_platform():
    return XiaohongshuPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _publish_single_video / 排期 / 账号名 运行 publish_video,返回 (result, calls)。"""
    single = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch('impl.xiaohongshu.platform._publish_single_video', single), \
         patch('impl.xiaohongshu.platform.parse_schedule_time', pst), \
         patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()):
        result = platform.publish_video(**kwargs)
    return result, single, pst


# ── 前置校验:话题总数 ≤ 10 ──────────────────────────────────────────────────

class TestTopicPreflight:
    def test_desc_hashtags_plus_tags_over_10_raises(self):
        inst = _make_platform()
        desc = ' '.join(f'#话题{i}' for i in range(6))  # 6 个 desc 话题
        tags = [f't{i}' for i in range(5)]             # + 5 标签 = 11
        with pytest.raises(ValueError, match="话题总数 11 超过 10"):
            _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'], desc=desc, tags=tags)

    def test_exactly_10_topics_ok(self):
        inst = _make_platform()
        desc = ' '.join(f'#话题{i}' for i in range(5))
        tags = [f't{i}' for i in range(5)]  # 5 + 5 = 10
        result, single, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'], desc=desc, tags=tags)
        assert result is True
        assert single.await_count == 1

    def test_desc_without_hashtags_plus_10_tags_ok(self):
        inst = _make_platform()
        desc = '无话题描述'
        tags = [f't{i}' for i in range(10)]
        result, single, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'], desc=desc, tags=tags)
        assert result is True
        assert single.await_count == 1

    def test_fail_logs_error(self):
        inst = _make_platform()
        logger = MagicMock()
        desc = ' '.join(f'#话题{i}' for i in range(11))
        with patch('impl.xiaohongshu.platform.logger', logger):
            with pytest.raises(ValueError):
                _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'], desc=desc)
            assert any(
                c.args[0] == '[发布视频] 小红书前置校验失败: %s'
                for c in logger.error.call_args_list
            )


# ── 方向感知封面选择 ────────────────────────────────────────────────────────

class TestDirectionalCover:
    def test_horizontal_prefers_landscape(self):
        inst = _make_platform()
        _, single, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            video_orientation='horizontal',
            thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
            thumbnail_path='/legacy.png',
        )
        assert single.await_args.kwargs['thumbnail_path'] == '/l.png'

    def test_vertical_prefers_portrait(self):
        inst = _make_platform()
        _, single, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            video_orientation='vertical',
            thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
            thumbnail_path='/legacy.png',
        )
        assert single.await_args.kwargs['thumbnail_path'] == '/p.png'

    def test_unknown_orientation_prefers_portrait(self):
        """未知方向默认竖版优先(小红书是竖版优先平台)。"""
        inst = _make_platform()
        _, single, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
        )
        assert single.await_args.kwargs['thumbnail_path'] == '/p.png'

    def test_no_cover_empty_string(self):
        inst = _make_platform()
        _, single, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert single.await_args.kwargs['thumbnail_path'] == ''


# ── XHS compat 排期 + 编排 ──────────────────────────────────────────────────

class TestScheduleAndOrchestration:
    def test_immediate_sets_publish_date_zero(self):
        """XHS compat: 无定时 → publish_datetimes 归一化为 0。"""
        inst = _make_platform()
        _, single, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert single.await_args.kwargs['publish_date'] == 0
        assert single.await_args.kwargs['publish_strategy'] == 'immediate'

    def test_timer_without_time_keeps_list(self):
        """enableTimer=True 但无 schedule_time_str → 保持列表(不归一化 0)。"""
        inst = _make_platform()
        dt = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=[dt])
        single = AsyncMock()
        with patch('impl.xiaohongshu.platform._publish_single_video', single), \
             patch('impl.xiaohongshu.platform.parse_schedule_time', pst), \
             patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()):
            inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json'], enableTimer=True)
        assert single.await_args.kwargs['publish_date'] == dt

    def test_scheduled_strategy(self):
        inst = _make_platform()
        dt = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=[dt])
        single = AsyncMock()
        with patch('impl.xiaohongshu.platform._publish_single_video', single), \
             patch('impl.xiaohongshu.platform.parse_schedule_time', pst), \
             patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()):
            inst.publish_video(
                title='T', files=['/v.mp4'], account_file=['a.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            )
        assert single.await_args.kwargs['publish_date'] == dt
        assert single.await_args.kwargs['publish_strategy'] == 'scheduled'

    def test_cartesian_product_2files_2accounts(self):
        inst = _make_platform()
        result, single, _ = _run_publish(
            inst, title='T', files=['/v1.mp4', '/v2.mp4'],
            account_file=['a.json', 'b.json'], desc='d',
        )
        assert result is True
        assert single.await_count == 4
        for i, call in enumerate(single.await_args_list):
            assert call.kwargs['file_path'] == f'/v{i // 2 + 1}.mp4'
            assert call.kwargs['account_file'] == str(Path(BASE_DIR / 'cookiesFile' / f'{"ab"[i % 2]}.json'))

    def test_xhs_specific_param_passthrough(self):
        inst = _make_platform()
        _, single, _ = _run_publish(
            inst,
            title='标题', files=['/v.mp4'], tags=['t1'], account_file=['a.json'],
            desc='描述', ai_content='原创',
            xhs_collection_id='c1', xhs_collection_name='合集A',
            xhs_source_type='self', xhs_shoot_location='北京',
            xhs_shoot_date='2026-08-01', xhs_repost_source='https://example.com',
        )
        call = single.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['ai_content'] == '原创'
        assert call.kwargs['collection_id'] == 'c1'
        assert call.kwargs['collection_name'] == '合集A'
        assert call.kwargs['xhs_source_type'] == 'self'
        assert call.kwargs['xhs_shoot_location'] == '北京'
        assert call.kwargs['xhs_shoot_date'] == '2026-08-01'
        assert call.kwargs['xhs_repost_source'] == 'https://example.com'

    def test_create_browser_fns_injected(self):
        """create_browser/create_context 以函数注入方式传给模块级 _publish_single_video。"""
        inst = _make_platform()
        _, single, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert single.await_args.kwargs['create_browser_fn'] == inst.create_browser
        assert single.await_args.kwargs['create_context_fn'] == inst.create_context

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        result, single, _ = _run_publish(inst, title='T')
        assert result is True
        assert single.await_count == 0
