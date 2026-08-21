"""CSDN publish_video 编排层契约测试（T23）。

publish_video(同步) 内联 async _run(): 固定横版封面(landscape or portrait,
不按视频方向) → 排期(标量兜底) → 文件×账号笛卡尔积 → _upload_single_video。
特有: recommend 参数。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.csdn.platform import CsdnPlatform


def _make_platform():
    return CsdnPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_single_video / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_single_video', upload), \
         patch('impl.csdn.platform.parse_schedule_time', pst), \
         patch('impl.csdn.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.csdn.platform.bind_account_name', MagicMock()):
        result = platform.publish_video(**kwargs)
    return result, upload, pst


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

    def test_fixed_landscape_cover_preferred(self):
        """CSDN 固定横版封面: 横版优先, 竖版兜底, 不按视频方向选择。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/l.png'

    def test_fixed_cover_portrait_fallback(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_portrait_path='/p.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/p.png'

    def test_no_cover_empty(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        # CSDN 无封面时透传空串(非 None)
        assert upload.await_args.kwargs['thumbnail_path'] == ''

    def test_param_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst,
            title='标题', files=['/v.mp4'], tags=['t1'], account_file=['a.json'],
            desc='描述', recommend=True,
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['recommend'] is True

    def test_recommend_default_false(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['recommend'] is False

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
        with patch.object(inst, '_upload_single_video', upload), \
             patch('impl.csdn.platform.parse_schedule_time', pst), \
             patch('impl.csdn.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.csdn.platform.bind_account_name', MagicMock()):
            inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            )
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]

    def test_schedule_non_list_scalar_fallback(self):
        inst = _make_platform()
        dt = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=dt)
        upload = AsyncMock()
        with patch.object(inst, '_upload_single_video', upload), \
             patch('impl.csdn.platform.parse_schedule_time', pst), \
             patch('impl.csdn.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.csdn.platform.bind_account_name', MagicMock()):
            inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            )
        for call in upload.await_args_list:
            assert call.kwargs['publish_date'] == dt

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(inst, title='T')
        assert result is True
        assert upload.await_count == 0
