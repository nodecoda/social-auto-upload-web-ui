"""爱奇艺 publish_video 编排层契约测试（T17b）。

publish_video(async) 高层编排: 封面优先级(竖版>legacy 单图>横版) →
parse_schedule_time 排期 → 文件×账号笛卡尔积 → _upload_one_video。
返回值聚合: 任一 _upload_one_video 返回 False → overall_success False。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.iqiyi.platform import IqiyiPlatform


def _make_platform():
    return IqiyiPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_one_video / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock(return_value=True)
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_one_video', upload), \
         patch('impl.iqiyi.platform.parse_schedule_time', pst), \
         patch('impl.iqiyi.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.iqiyi.platform.bind_account_name', MagicMock()):
        result = _run_async(platform.publish_video(**kwargs))
    return result, upload, pst


def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


# ── 封面选择 ────────────────────────────────────────────────────────────────

class TestCoverSelection:
    def test_portrait_priority(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_portrait_path='/p.png', thumbnail_path='/legacy.png',
            thumbnail_landscape_path='/l.png',
        )
        call = upload.await_args
        assert call.kwargs['cover_path'] == '/p.png'
        assert call.kwargs['landscape_cover'] == '/l.png'

    def test_legacy_thumbnail_fallback(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_path='/legacy.png', thumbnail_landscape_path='/l.png',
        )
        assert upload.await_args.kwargs['cover_path'] == '/legacy.png'

    def test_landscape_fallback(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_path='/l.png',
        )
        assert upload.await_args.kwargs['cover_path'] == '/l.png'

    def test_no_cover_none(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        call = upload.await_args
        assert call.kwargs['cover_path'] is None
        assert call.kwargs['landscape_cover'] is None

    def test_landscape_169_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_169_path='/l169.png',
        )
        assert upload.await_args.kwargs['landscape_cover_169'] == '/l169.png'


# ── 返回值聚合 ──────────────────────────────────────────────────────────────

class TestOverallSuccess:
    def test_all_true_returns_true(self):
        inst = _make_platform()
        result, _, _ = _run_publish(
            inst, title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
        )
        assert result is True

    def test_any_false_returns_false(self):
        inst = _make_platform()
        upload = AsyncMock(side_effect=[True, False, True, True])
        with patch.object(inst, '_upload_one_video', upload), \
             patch('impl.iqiyi.platform.parse_schedule_time', MagicMock(return_value=[None] * 2)), \
             patch('impl.iqiyi.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.iqiyi.platform.bind_account_name', MagicMock()):
            result = _run_async(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
            ))
        assert result is False


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
            desc='描述', enableTimer=True, schedule_time_str='2026-08-21 10:00',
            creation_declaration='原创', risk_warning='风险提示',
            enable_cash_activity=True,
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['enableTimer'] is True
        assert call.kwargs['creation_declaration'] == '原创'
        assert call.kwargs['risk_warning'] == '风险提示'
        assert call.kwargs['enable_cash_activity'] is True

    def test_cookie_path_resolution(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['u1.json'])
        assert upload.await_args.kwargs['account_file'] == str(Path(BASE_DIR / 'cookiesFile' / 'u1.json'))

    def test_strategy_log_immediate(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock(return_value=True)), \
             patch('impl.iqiyi.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.iqiyi.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.iqiyi.platform.bind_account_name', MagicMock()):
            _run_async(inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json']))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('immediate',)
            for c in logger.info.call_args_list
        )

    def test_strategy_log_scheduled(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock(return_value=True)), \
             patch('impl.iqiyi.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.iqiyi.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.iqiyi.platform.bind_account_name', MagicMock()):
            _run_async(inst.publish_video(
                title='T', files=['/v.mp4'], account_file=['a.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('scheduled',)
            for c in logger.info.call_args_list
        )

    def test_schedule_time_per_file_index(self):
        inst = _make_platform()
        dt1 = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        dt2 = datetime(2026, 8, 22, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=[dt1, dt2])
        upload = AsyncMock(return_value=True)
        with patch.object(inst, '_upload_one_video', upload), \
             patch('impl.iqiyi.platform.parse_schedule_time', pst), \
             patch('impl.iqiyi.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.iqiyi.platform.bind_account_name', MagicMock()):
            _run_async(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(inst, title='T')
        assert result is True
        assert upload.await_count == 0
