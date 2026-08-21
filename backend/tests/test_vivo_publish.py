"""VIVO publish_video 编排层契约测试（T17）。

publish_video(async) 高层编排: 平台特有参数(位置/同步/声明/隐私/下载权限) →
策略选择 → parse_schedule_time 排期 → 文件×账号笛卡尔积 → _upload_one_video。
dry_run 由环境变量 VIVO_DRY_RUN=1 控制。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.vivo.platform import VivoPlatform


def _make_platform():
    return VivoPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_one_video / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_one_video', upload), \
         patch('impl.vivo.platform.parse_schedule_time', pst), \
         patch('impl.vivo.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.vivo.platform.bind_account_name', MagicMock()):
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

    def test_vivo_specific_param_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst,
            title='标题', files=['/v.mp4'], tags=['t1'], account_file=['a.json'],
            desc='描述', vivo_location_name='北京', vivo_distribution=True,
            vivo_declaration='原创', vivo_privacy='仅自己可见',
            vivo_download_permission='禁止下载',
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['vivo_location_name'] == '北京'
        assert call.kwargs['vivo_distribution'] is True
        assert call.kwargs['vivo_declaration'] == '原创'
        assert call.kwargs['vivo_privacy'] == '仅自己可见'
        assert call.kwargs['vivo_download_permission'] == '禁止下载'

    def test_vivo_defaults(self):
        """未传 VIVO 特有参数时使用平台默认值。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        call = upload.await_args
        assert call.kwargs['vivo_location_name'] == ''
        assert call.kwargs['vivo_distribution'] is False
        assert call.kwargs['vivo_declaration'] == ''
        assert call.kwargs['vivo_privacy'] == '公开'
        assert call.kwargs['vivo_download_permission'] == '允许'

    def test_dry_run_enabled_by_env(self):
        inst = _make_platform()
        with patch.dict('os.environ', {'VIVO_DRY_RUN': '1'}):
            _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['dry_run'] is True

    def test_dry_run_disabled_by_default(self):
        inst = _make_platform()
        with patch.dict('os.environ', {}, clear=False):
            _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['dry_run'] is False

    def test_dry_run_ignores_non_one_env(self):
        inst = _make_platform()
        with patch.dict('os.environ', {'VIVO_DRY_RUN': '0'}):
            _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['dry_run'] is False

    def test_covers_normalized_to_none(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_portrait_path='', thumbnail_landscape_path='',
        )
        call = upload.await_args
        assert call.kwargs['thumbnail_portrait_path'] is None
        assert call.kwargs['thumbnail_landscape_path'] is None

    def test_cover_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_portrait_path='/p.png', thumbnail_landscape_path='/l.png',
        )
        call = upload.await_args
        assert call.kwargs['thumbnail_portrait_path'] == '/p.png'
        assert call.kwargs['thumbnail_landscape_path'] == '/l.png'

    def test_cookie_path_resolution(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['u1.json'])
        assert upload.await_args.kwargs['account_file'] == str(Path(BASE_DIR / 'cookiesFile' / 'u1.json'))

    def test_strategy_immediate(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['publish_strategy'] == 'immediate'

    def test_strategy_scheduled(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            enableTimer=True, schedule_time_str='2026-08-21 10:00',
        )
        assert upload.await_args.kwargs['publish_strategy'] == 'scheduled'

    def test_schedule_time_per_file_index(self):
        inst = _make_platform()
        dt1 = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        dt2 = datetime(2026, 8, 22, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=[dt1, dt2])
        upload = AsyncMock()
        with patch.object(inst, '_upload_one_video', upload), \
             patch('impl.vivo.platform.parse_schedule_time', pst), \
             patch('impl.vivo.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.vivo.platform.bind_account_name', MagicMock()):
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
