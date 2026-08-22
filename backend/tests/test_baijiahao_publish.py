"""百家号 publish_video 编排层契约测试（T16a）。

publish_video 是高层编排：desc+tags 前置校验(≤10 标签/≤50 字符,emoji×3) →
sync 包装 _upload_all → parse_schedule_time 排期(按文件索引) → 文件×账号遍历 →
_upload_one_video(本批 mock 掉,只测编排契约)。
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.baijiahao.platform import BaijiahaoPlatform


def _make_platform():
    return BaijiahaoPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_one_video / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_one_video', upload), \
         patch('impl.baijiahao.platform.parse_schedule_time', pst), \
         patch('impl.baijiahao.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.baijiahao.platform.bind_account_name', MagicMock()):
        result = asyncio.run(platform.publish_video(**kwargs))
    return result, upload, pst




# ── 前置校验 ───────────────────────────────────────────────────────────────

class TestPublishVideoPreflight:
    def test_tags_over_10_raises(self):
        inst = _make_platform()
        with pytest.raises(ValueError, match="最多 10 个标签"):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], tags=[f't{i}' for i in range(11)]))

    def test_desc_tags_over_50_chars_raises(self):
        inst = _make_platform()
        desc = '长' * 60
        with pytest.raises(ValueError, match=r"总字符数.*超过 50"):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], desc=desc))

    def test_emoji_counts_as_3_raises(self):
        inst = _make_platform()
        desc = '😀' * 18  # 18 emoji = 54 字符 > 50
        with pytest.raises(ValueError, match="超过 50"):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], desc=desc))

    def test_valid_params_do_not_raise(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'], desc='ok', tags=['a', 'b'])
        assert result is True
        assert upload.await_count == 1

    def test_empty_desc_and_tags_ok(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert result is True
        assert upload.await_count == 1

    def test_validate_fail_logs_error(self):
        inst = _make_platform()
        with patch('impl.baijiahao.platform.logger') as logger:
            with pytest.raises(ValueError):
                asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], tags=[f't{i}' for i in range(11)]))
            assert any(
                c.args[0] == '[发布视频] 百家号前置校验失败: %s' and c.args[1:] == ('百家号最多 10 个标签,当前 11 个',)
                for c in logger.error.call_args_list
            )


# ── _upload_all 编排 ───────────────────────────────────────────────────────

class TestUploadAllOrchestration:
    def test_cartesian_product_2files_2accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(
            inst,
            title='T', files=['/v1.mp4', '/v2.mp4'],
            account_file=['a.json', 'b.json'], desc='d',
        )
        assert result is True
        assert upload.await_count == 4
        # 文件外层循环 × 账号内层循环: 同文件两次调用共享同一 publish_date
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['file_path'] == f'/v{i // 2 + 1}.mp4'
            assert call.kwargs['account_file'].endswith(f'{"ab"[i % 2]}.json')

    def test_single_file_single_account(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_count == 1
        call = upload.await_args
        assert call.kwargs['title'] == 'T'
        assert call.kwargs['file_path'] == '/v.mp4'

    def test_param_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst,
            title='标题', files=['/v.mp4'], tags=['t1', 't2'], account_file=['a.json'],
            thumbnail_landscape_path='/cover_l.png', thumbnail_portrait_path='/cover_p.png',
            thumbnail_landscape_169_path='/cover_169.png', desc='描述',
            creation_declaration='AI生成', supplementary_declaration='虚构', ai_content=True,
        )
        call = upload.await_args
        assert call.kwargs['tags'] == ['t1', 't2']
        assert call.kwargs['thumbnail_landscape_path'] == '/cover_l.png'
        assert call.kwargs['thumbnail_portrait_path'] == '/cover_p.png'
        assert call.kwargs['thumbnail_landscape_169_path'] == '/cover_169.png'
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['creation_declaration'] == 'AI生成'
        assert call.kwargs['supplementary_declaration'] == '虚构'
        assert call.kwargs['ai_content'] is True

    def test_cookie_path_resolution(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['u1.json'])
        call = upload.await_args
        assert call.kwargs['account_file'] == str(Path(BASE_DIR / 'cookiesFile' / 'u1.json'))

    def test_schedule_time_per_file_index(self):
        inst = _make_platform()
        dt1 = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        dt2 = datetime(2026, 8, 22, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=[dt1, dt2])
        upload = AsyncMock()
        with patch.object(inst, '_upload_one_video', upload), \
             patch('impl.baijiahao.platform.parse_schedule_time', pst), \
             patch('impl.baijiahao.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.baijiahao.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        # parse_schedule_time 收到 (schedule_time_str, 文件数, enableTimer, videos_per_day, daily_times, start_days)
        assert pst.call_args.args[0] == '2026-08-21 10:00'
        assert pst.call_args.args[1] == 2
        assert pst.call_args.args[2] is True
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]

    def test_strategy_immediate_log(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.baijiahao.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock()), \
             patch('impl.baijiahao.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.baijiahao.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.baijiahao.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json']))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('immediate',)
            for c in logger.info.call_args_list
        )

    def test_strategy_scheduled_log(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.baijiahao.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock()), \
             patch('impl.baijiahao.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.baijiahao.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.baijiahao.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(
                title='T', files=['/v.mp4'], account_file=['a.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('scheduled',)
            for c in logger.info.call_args_list
        )

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T')
        assert upload.await_count == 0


