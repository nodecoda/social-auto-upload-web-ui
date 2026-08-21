"""淘宝光合 publish_video 编排层契约测试（T23）。

publish_video(同步) 内联 async _run(): link_items 规范化(按 link_type 选源,
字符串→{title}, 最多 6 个) → 方向封面(landscape→169>横>916>竖) → 排期 →
文件×账号笛卡尔积 → _upload_single_video。
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.taobao_guanghe.platform import TaobaoGuanghePlatform


def _make_platform():
    return TaobaoGuanghePlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_single_video / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_single_video', upload), \
         patch('impl.taobao_guanghe.platform.parse_schedule_time', pst), \
         patch('impl.taobao_guanghe.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.taobao_guanghe.platform.bind_account_name', MagicMock()):
        result = platform.publish_video(**kwargs)
    return result, upload, pst


# ── link_items 规范化 ──────────────────────────────────────────────────────

class TestLinkNormalization:
    def test_product_type_uses_products(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            guangheLinkType='product', guangheProducts=['商品A', {'title': '商品B', 'id': 2}],
            guangheShops=['店铺X'],
        )
        assert upload.await_args.kwargs['link_items'] == [{'title': '商品A'}, {'title': '商品B', 'id': 2}]

    def test_shop_type_uses_shops(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            guangheLinkType='shop', guangheProducts=['商品A'], guangheShops=['店铺X'],
        )
        assert upload.await_args.kwargs['link_items'] == [{'title': '店铺X'}]

    def test_no_link_type_empty_items(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            guangheProducts=['商品A'],
        )
        assert upload.await_args.kwargs['link_items'] == []
        assert upload.await_args.kwargs['link_type'] == ''

    def test_link_items_truncated_to_6(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            guangheLinkType='product', guangheProducts=[f'p{i}' for i in range(10)],
        )
        assert len(upload.await_args.kwargs['link_items']) == 6

    def test_link_type_stripped(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            guangheLinkType=' product ', guangheProducts=['商品A'],
        )
        assert upload.await_args.kwargs['link_type'] == 'product'


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

    def test_unknown_format_prefers_916(self):
        """未知方向也走竖版分支(9:16 优先)。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_169_path='/l169.png', thumbnail_portrait_916_path='/p916.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/p916.png'

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

    def test_claim_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            desc='描述', guanghe_claim='创作者声明',
        )
        call = upload.await_args
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['claim'] == '创作者声明'

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
             patch('impl.taobao_guanghe.platform.parse_schedule_time', pst), \
             patch('impl.taobao_guanghe.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.taobao_guanghe.platform.bind_account_name', MagicMock()):
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
