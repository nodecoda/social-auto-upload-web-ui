"""京东(京麦) publish_video 编排层契约测试（T22）。

publish_video(同步) 内联 _run(): files/account_file 空 → ValueError(京东特有) →
jd_novel/jd_products 规范化 → 方向封面(landscape→169>横>916>竖) → 排期 →
文件×账号笛卡尔积 → _upload_single_video。
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
from impl.jd.platform import JdPlatform


def _make_platform():
    return JdPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_single_video / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_single_video', upload), \
         patch('impl.jd.platform.parse_schedule_time', pst), \
         patch('impl.jd.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.jd.platform.bind_account_name', MagicMock()):
        result = asyncio.run(platform.publish_video(**kwargs))
    return result, upload, pst


# ── 空输入校验(京东特有,非静默跳过) ────────────────────────────────────────

class TestEmptyInputValidation:
    def test_empty_files_raises(self):
        inst = _make_platform()
        with pytest.raises(ValueError, match="files 不能为空"):
            _run_publish(inst, title='T', account_file=['a.json'])

    def test_empty_account_file_raises(self):
        inst = _make_platform()
        with pytest.raises(ValueError, match="account_file 不能为空"):
            _run_publish(inst, title='T', files=['/v.mp4'])


# ── jd_novel / jd_products 规范化 ──────────────────────────────────────────

class TestNovelAndProductsNormalization:
    def test_novel_str_to_dict(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            jd_novel='小说标题',
        )
        assert upload.await_args.kwargs['jd_novel'] == {'title': '小说标题'}

    def test_novel_dict_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            jd_novel={'title': '小说', 'author': '作者'},
        )
        assert upload.await_args.kwargs['jd_novel'] == {'title': '小说', 'author': '作者'}

    def test_novel_empty_str_stays_empty(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_args.kwargs['jd_novel'] == ''

    def test_products_str_to_dict(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            jd_products=['商品A', '商品B'],
        )
        assert upload.await_args.kwargs['link_items'] == [{'title': '商品A'}, {'title': '商品B'}]

    def test_products_dict_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            jd_products=[{'title': 'A', 'id': 1}],
        )
        assert upload.await_args.kwargs['link_items'] == [{'title': 'A', 'id': 1}]

    def test_products_truncated_to_10(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            jd_products=[f'p{i}' for i in range(15)],
        )
        assert len(upload.await_args.kwargs['link_items']) == 10

    def test_related_type_and_declaration_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            jd_related_type='商品', jd_declaration='原创',
        )
        call = upload.await_args
        assert call.kwargs['related_type'] == '商品'
        assert call.kwargs['jd_declaration'] == '原创'


# ── 方向封面 + 编排 ─────────────────────────────────────────────────────────

class TestDirectionalCoverAndOrchestration:
    def test_landscape_prefers_169(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'], video_format='landscape',
            thumbnail_landscape_169_path='/l169.png', thumbnail_landscape_path='/l.png',
            thumbnail_portrait_916_path='/p916.png', thumbnail_portrait_path='/p.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/l169.png'

    def test_portrait_prefers_916(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'], video_format='portrait',
            thumbnail_landscape_169_path='/l169.png', thumbnail_landscape_path='/l.png',
            thumbnail_portrait_916_path='/p916.png', thumbnail_portrait_path='/p.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/p916.png'

    def test_cartesian_product_2files_2accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(
            inst, title='T', files=['/v1.mp4', '/v2.mp4'],
            account_file=['a.json', 'b.json'],
        )
        assert result is True
        assert upload.await_count == 4
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['file_path'] == f'/v{i // 2 + 1}.mp4'
            assert call.kwargs['account_file'].endswith(f'{"ab"[i % 2]}.json')

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
             patch('impl.jd.platform.parse_schedule_time', pst), \
             patch('impl.jd.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.jd.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]
