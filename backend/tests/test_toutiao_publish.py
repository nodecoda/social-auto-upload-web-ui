"""今日头条 publish_video 编排层契约测试（T17）。

publish_video(async) 是高层编排: creation_declaration 字符串→列表解析 →
策略选择 → parse_schedule_time 排期 → 文件×账号笛卡尔积 → _upload_one_video。
封面空串→None 归一化。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.toutiao.platform import ToutiaoPlatform


def _make_platform():
    return ToutiaoPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_one_video / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_one_video', upload), \
         patch('impl.toutiao.platform.parse_schedule_time', pst), \
         patch('impl.toutiao.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.toutiao.platform.bind_account_name', MagicMock()):
        result = _run_async(platform.publish_video(**kwargs))
    return result, upload, pst


def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


# ── creation_declaration 解析 ───────────────────────────────────────────────

class TestCreationDeclarationParsing:
    def test_comma_separated_string_to_list(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            creation_declaration='AI生成, 原创',
        )
        assert upload.await_args.kwargs['creation_declaration'] == ['AI生成', '原创']

    def test_list_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            creation_declaration=['原创'],
        )
        assert upload.await_args.kwargs['creation_declaration'] == ['原创']

    def test_empty_string_to_empty_list(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            creation_declaration='',
        )
        assert upload.await_args.kwargs['creation_declaration'] == []

    def test_other_type_to_empty_list(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            creation_declaration=123,
        )
        assert upload.await_args.kwargs['creation_declaration'] == []


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
            desc='描述', thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
            thumbnail_landscape_169_path='/l169.png', thumbnail_portrait_916_path='/p916.png',
            enable_generate_image=False, collection_id='c1', extend_link=True,
            extend_link_url='https://example.com',
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['thumbnail_landscape_path'] == '/l.png'
        assert call.kwargs['thumbnail_portrait_path'] == '/p.png'
        assert call.kwargs['thumbnail_landscape_169_path'] == '/l169.png'
        assert call.kwargs['thumbnail_portrait_916_path'] == '/p916.png'
        assert call.kwargs['enable_generate_image'] is False
        assert call.kwargs['collection_id'] == 'c1'
        assert call.kwargs['extend_link'] is True
        assert call.kwargs['extend_link_url'] == 'https://example.com'

    def test_empty_cover_normalized_to_none(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_path='', thumbnail_portrait_path='',
            thumbnail_landscape_169_path='', thumbnail_portrait_916_path='',
        )
        call = upload.await_args
        assert call.kwargs['thumbnail_landscape_path'] is None
        assert call.kwargs['thumbnail_portrait_path'] is None
        assert call.kwargs['thumbnail_landscape_169_path'] is None
        assert call.kwargs['thumbnail_portrait_916_path'] is None

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
             patch('impl.toutiao.platform.parse_schedule_time', pst), \
             patch('impl.toutiao.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.toutiao.platform.bind_account_name', MagicMock()):
            _run_async(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        assert pst.call_args.args[0] == '2026-08-21 10:00'
        assert pst.call_args.args[1] == 2
        assert pst.call_args.args[2] is True
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(inst, title='T')
        assert result is True
        assert upload.await_count == 0

    def test_enable_generate_image_default_true(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['enable_generate_image'] is True
