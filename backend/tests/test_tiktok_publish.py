"""TikTok publish_video 编排层契约测试（T16b）。

publish_video(sync wrapper) → _upload_all: 封面优先级(portrait>landscape>legacy) →
parse_schedule_time 排期(按文件索引,非 list 兜底) → 文件×账号笛卡尔积 →
_upload_single(注意方法名,非 _upload_one_video)。
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.tiktok.platform import TiktokPlatform


def _make_platform():
    return TiktokPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_single / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_single', upload), \
         patch('impl.tiktok.platform.parse_schedule_time', pst), \
         patch('impl.tiktok.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.tiktok.platform.bind_account_name', MagicMock()):
        result = asyncio.run(platform.publish_video(**kwargs))
    return result, upload, pst


# ── publish_video sync wrapper ──────────────────────────────────────────────

class TestPublishVideoSync:
    def test_returns_true_and_calls_upload_all(self):
        inst = _make_platform()
        with patch.object(inst, '_upload_all', AsyncMock()) as upload_all:
            assert asyncio.run(inst.publish_video(title='T', files=['/v.mp4'])) is True
            upload_all.assert_awaited_once()


# ── _upload_all 编排 ────────────────────────────────────────────────────────

class TestUploadAllOrchestration:
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

    def test_thumbnail_priority_portrait(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_portrait_path='/p.png', thumbnail_landscape_path='/l.png',
            thumbnail_path='/legacy.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/p.png'

    def test_thumbnail_fallback_landscape(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_path='/l.png', thumbnail_path='/legacy.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/l.png'

    def test_thumbnail_fallback_legacy(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_path='/legacy.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/legacy.png'

    def test_thumbnail_none(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['thumbnail_path'] is None

    def test_param_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='标题', files=['/v.mp4'], tags=['t1'], account_file=['a.json'],
            desc='描述', ai_content=True,
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['ai_content'] is True

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
        with patch.object(inst, '_upload_single', upload), \
             patch('impl.tiktok.platform.parse_schedule_time', pst), \
             patch('impl.tiktok.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.tiktok.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        assert pst.call_args.args[0] == '2026-08-21 10:00'
        assert pst.call_args.args[1] == 2
        assert pst.call_args.args[2] is True
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]

    def test_schedule_non_list_scalar_fallback(self):
        """parse_schedule_time 返回非 list(单个值)时所有文件共用该值。"""
        inst = _make_platform()
        dt = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=dt)
        upload = AsyncMock()
        with patch.object(inst, '_upload_single', upload), \
             patch('impl.tiktok.platform.parse_schedule_time', pst), \
             patch('impl.tiktok.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.tiktok.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        for call in upload.await_args_list:
            assert call.kwargs['publish_date'] == dt

    def test_strategy_immediate_log(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.tiktok.platform.logger', logger), \
             patch.object(inst, '_upload_single', AsyncMock()), \
             patch('impl.tiktok.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.tiktok.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.tiktok.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json']))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('immediate',)
            for c in logger.info.call_args_list
        )

    def test_strategy_scheduled_log(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.tiktok.platform.logger', logger), \
             patch.object(inst, '_upload_single', AsyncMock()), \
             patch('impl.tiktok.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.tiktok.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.tiktok.platform.bind_account_name', MagicMock()):
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
