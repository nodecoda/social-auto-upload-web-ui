"""知乎 publish_video 编排层契约测试（T21）。

publish_video(同步) 内联 async _run(): 方向感知封面选择(素材表 orientation
优先, 无记录兜底前端 videoFormat) → 排期 → 文件×账号笛卡尔积 →
_upload_single_video。creation_declaration 默认「内容无需标注」。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.zhihu.platform import ZhihuPlatform


def _make_platform():
    return ZhihuPlatform()


def _run_publish(platform, orientation='', **kwargs):
    """以 mock _upload_single_video / 排期 / 账号名 / 素材方向 运行 publish_video。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_single_video', upload), \
         patch('impl.zhihu.platform.parse_schedule_time', pst), \
         patch('impl.zhihu.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.zhihu.platform.bind_account_name', MagicMock()), \
         patch('impl.zhihu.platform._get_video_orientation', return_value=orientation):
        result = platform.publish_video(**kwargs)
    return result, upload, pst


# ── 方向感知封面选择 ────────────────────────────────────────────────────────

class TestDirectionalCover:
    def test_vertical_prefers_916(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, orientation='vertical',
            title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_portrait_916_path='/p916.png', thumbnail_portrait_path='/p.png',
            thumbnail_landscape_path='/l.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/p916.png'

    def test_vertical_fallback_portrait(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, orientation='vertical',
            title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_portrait_path='/p.png', thumbnail_landscape_path='/l.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/p.png'

    def test_horizontal_prefers_169(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, orientation='horizontal',
            title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_169_path='/l169.png', thumbnail_landscape_path='/l.png',
            thumbnail_portrait_path='/p.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/l169.png'

    def test_horizontal_fallback_landscape(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, orientation='horizontal',
            title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/l.png'

    def test_unknown_orientation_frontend_portrait(self):
        """素材表无方向记录, 兜底前端 videoFormat=portrait → 竖版优先。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, orientation='',
            title='T', files=['/v.mp4'], account_file=['a.json'], video_format='portrait',
            thumbnail_portrait_916_path='/p916.png', thumbnail_portrait_path='/p.png',
            thumbnail_landscape_path='/l.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/p916.png'

    def test_unknown_orientation_frontend_landscape(self):
        """素材表无方向记录, 前端默认 landscape → 横版优先。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, orientation='',
            title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_169_path='/l169.png', thumbnail_landscape_path='/l.png',
            thumbnail_portrait_path='/p.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/l169.png'

    def test_no_cover_empty(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, orientation='horizontal', title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['thumbnail_path'] == ''


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
            desc='描述', category='科技', creation_declaration='内容由AI生成',
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['category'] == '科技'
        assert call.kwargs['creation_declaration'] == '内容由AI生成'

    def test_creation_declaration_default(self):
        """未传 creation_declaration 时默认「内容无需标注」。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['creation_declaration'] == '内容无需标注'

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
             patch('impl.zhihu.platform.parse_schedule_time', pst), \
             patch('impl.zhihu.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.zhihu.platform.bind_account_name', MagicMock()), \
             patch('impl.zhihu.platform._get_video_orientation', return_value='horizontal'):
            inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            )
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(inst, title='T')
        assert result is True
        assert upload.await_count == 0
