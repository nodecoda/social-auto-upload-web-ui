"""YouTube publish_video 编排层契约测试（T19）。

publish_video(async) 高层编排: 排期(按文件索引, 非 list 标量兜底) →
文件×账号笛卡尔积 → _upload_one(注意方法名)。特有参数:
audience(默认 not_kids) / altered_content(默认 False)。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.youtube.platform import YoutubePlatform


def _make_platform():
    return YoutubePlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_one / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_one', upload), \
         patch('impl.youtube.platform.parse_schedule_time', pst), \
         patch('impl.youtube.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.youtube.platform.bind_account_name', MagicMock()):
        result = _run_async(platform.publish_video(**kwargs))
    return result, upload, pst


def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


# ── publish_video 编排 ──────────────────────────────────────────────────────

class TestPublishVideoOrchestration:
    def test_cartesian_product_2files_2accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(
            inst, title='T', files=['/v1.mp4', '/v2.mp4'],
            account_file=['a.json', 'b.json'], desc='d',
        )
        assert result is True
        assert upload.await_count == 4
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['file_path'] == f'/v{i // 2 + 1}.mp4'
            assert call.kwargs['account_file'].endswith(f'{"ab"[i % 2]}.json')

    def test_param_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst,
            title='标题', files=['/v.mp4'], tags=['t1'], account_file=['a.json'],
            desc='描述', thumbnail_path='/cover.png', audience='kids',
            altered_content=True,
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['thumbnail_path'] == '/cover.png'
        assert call.kwargs['audience'] == 'kids'
        assert call.kwargs['altered_content'] is True

    def test_audience_default_not_kids(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['audience'] == 'not_kids'

    def test_altered_content_default_false(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['altered_content'] is False

    def test_cookie_path_resolution(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['u1.json'])
        assert upload.await_args.kwargs['account_file'] == str(Path(BASE_DIR / 'cookiesFile' / 'u1.json'))

    def test_schedule_time_per_file_index(self):
        inst = _make_platform()
        dt1 = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        dt2 = datetime(2026, 8, 22, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=[dt1, dt2])
        upload = AsyncMock()
        with patch.object(inst, '_upload_one', upload), \
             patch('impl.youtube.platform.parse_schedule_time', pst), \
             patch('impl.youtube.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.youtube.platform.bind_account_name', MagicMock()):
            _run_async(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]

    def test_schedule_non_list_scalar_fallback(self):
        inst = _make_platform()
        dt = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=dt)
        upload = AsyncMock()
        with patch.object(inst, '_upload_one', upload), \
             patch('impl.youtube.platform.parse_schedule_time', pst), \
             patch('impl.youtube.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.youtube.platform.bind_account_name', MagicMock()):
            _run_async(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        for call in upload.await_args_list:
            assert call.kwargs['publish_date'] == dt

    def test_strategy_log_immediate(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.youtube.platform.logger', logger), \
             patch.object(inst, '_upload_one', AsyncMock()), \
             patch('impl.youtube.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.youtube.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.youtube.platform.bind_account_name', MagicMock()):
            _run_async(inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json']))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('immediate',)
            for c in logger.info.call_args_list
        )

    def test_strategy_log_scheduled(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.youtube.platform.logger', logger), \
             patch.object(inst, '_upload_one', AsyncMock()), \
             patch('impl.youtube.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.youtube.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.youtube.platform.bind_account_name', MagicMock()):
            _run_async(inst.publish_video(
                title='T', files=['/v.mp4'], account_file=['a.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('scheduled',)
            for c in logger.info.call_args_list
        )

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(inst, title='T')
        assert result is True
        assert upload.await_count == 0
