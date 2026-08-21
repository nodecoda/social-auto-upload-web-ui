"""腾讯视频 publish_video 编排层契约测试（T17b）。

publish_video(async) 高层编排: 按视频方向选主封面(portrait: 916>竖版 /
landscape: 169>横版) + 互补封面 → creation_declaration 解析 → 排期 →
文件×账号笛卡尔积 → _upload_one_video。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.tencent_video.platform import TencentVideoPlatform


def _make_platform():
    return TencentVideoPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_one_video / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_one_video', upload), \
         patch('impl.tencent_video.platform.parse_schedule_time', pst), \
         patch('impl.tencent_video.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.tencent_video.platform.bind_account_name', MagicMock()):
        result = _run_async(platform.publish_video(**kwargs))
    return result, upload, pst


def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


# ── 方向感知封面选择 ────────────────────────────────────────────────────────

class TestDirectionalCoverSelection:
    def test_landscape_default_primary_169(self):
        """横版(默认): 主封面=169, 选填竖版=916, 不传选填横版。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_169_path='/l169.png', thumbnail_landscape_path='/l.png',
            thumbnail_portrait_916_path='/p916.png', thumbnail_portrait_path='/p.png',
        )
        call = upload.await_args
        assert call.kwargs['primary_cover'] == '/l169.png'
        assert call.kwargs['primary_aspect'] == '16:9'
        assert call.kwargs['extra_landscape_cover'] is None
        assert call.kwargs['extra_portrait_cover'] == '/p916.png'

    def test_landscape_fallback_plain_landscape(self):
        """横版无 169 时用普通横版封面。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_path='/l.png',
        )
        call = upload.await_args
        assert call.kwargs['primary_cover'] == '/l.png'
        assert call.kwargs['primary_aspect'] == '16:9'
        # 互补封面无值时空串透传(仅 primary 做 or None)
        assert call.kwargs['extra_portrait_cover'] == ''

    def test_portrait_primary_916(self):
        """竖版: 主封面=916(无则竖版), 选填横版=169, 不传选填竖版。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'], video_format='portrait',
            thumbnail_portrait_916_path='/p916.png', thumbnail_portrait_path='/p.png',
            thumbnail_landscape_169_path='/l169.png', thumbnail_landscape_path='/l.png',
        )
        call = upload.await_args
        assert call.kwargs['primary_cover'] == '/p916.png'
        assert call.kwargs['primary_aspect'] == 'portrait'
        assert call.kwargs['extra_landscape_cover'] == '/l169.png'
        assert call.kwargs['extra_portrait_cover'] is None

    def test_portrait_fallback_plain_portrait(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'], video_format='portrait',
            thumbnail_portrait_path='/p.png',
        )
        call = upload.await_args
        assert call.kwargs['primary_cover'] == '/p.png'
        assert call.kwargs['primary_aspect'] == 'portrait'

    def test_no_cover_primary_none(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        call = upload.await_args
        assert call.kwargs['primary_cover'] is None
        assert call.kwargs['extra_landscape_cover'] is None
        # 互补封面无值时空串透传(仅 primary 做 or None)
        assert call.kwargs['extra_portrait_cover'] == ''

    def test_video_format_default_landscape(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_169_path='/l169.png',
        )
        assert upload.await_args.kwargs['primary_aspect'] == '16:9'


# ── creation_declaration 解析 ───────────────────────────────────────────────

class TestCreationDeclarationParsing:
    def test_comma_separated_string_to_list(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            creation_declaration='AI生成, 原创',
        )
        assert upload.await_args.kwargs['creation_declarations'] == ['AI生成', '原创']

    def test_list_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            creation_declaration=['原创'],
        )
        assert upload.await_args.kwargs['creation_declarations'] == ['原创']

    def test_empty_to_empty_list(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['creation_declarations'] == []


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
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['enableTimer'] is True

    def test_cookie_path_resolution(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['u1.json'])
        assert upload.await_args.kwargs['account_file'] == str(Path(BASE_DIR / 'cookiesFile' / 'u1.json'))

    def test_strategy_log_immediate(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.tencent_video.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock()), \
             patch('impl.tencent_video.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.tencent_video.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.tencent_video.platform.bind_account_name', MagicMock()):
            _run_async(inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json']))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('immediate',)
            for c in logger.info.call_args_list
        )

    def test_strategy_log_scheduled(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.tencent_video.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock()), \
             patch('impl.tencent_video.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.tencent_video.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.tencent_video.platform.bind_account_name', MagicMock()):
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
        upload = AsyncMock()
        with patch.object(inst, '_upload_one_video', upload), \
             patch('impl.tencent_video.platform.parse_schedule_time', pst), \
             patch('impl.tencent_video.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.tencent_video.platform.bind_account_name', MagicMock()):
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
