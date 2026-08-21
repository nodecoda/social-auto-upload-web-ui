"""支付宝 publish_video 编排层契约测试（T16a）。

publish_video(sync wrapper) → _upload_all: 参数摘要日志 → 文件×账号笛卡尔积 →
_upload_one_video(本批 mock 掉)。含 author_statement / compilation / reprint_url /
video_format 等支付宝特有参数透传。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.alipay.platform import AlipayPlatform


def _make_platform():
    return AlipayPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_one_video / 账号名 运行 publish_video,返回 (result, upload)。"""
    upload = AsyncMock()
    with patch.object(platform, '_upload_one_video', upload), \
         patch('impl.alipay.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.alipay.platform.bind_account_name', MagicMock()):
        result = asyncio.run(platform.publish_video(**kwargs))
    return result, upload


# ── publish_video sync wrapper ──────────────────────────────────────────────

class TestPublishVideoSync:
    def test_returns_true_and_calls_upload_all(self):
        inst = _make_platform()
        with patch.object(inst, '_upload_all', AsyncMock()) as upload_all:
            assert asyncio.run(inst.publish_video(title='T', files=['/v.mp4'])) is True
            upload_all.assert_awaited_once()

    def test_empty_kwargs(self):
        inst = _make_platform()
        with patch.object(inst, '_upload_all', AsyncMock()) as upload_all:
            assert asyncio.run(inst.publish_video()) is True
            upload_all.assert_awaited_once()


# ── _upload_all 编排 ────────────────────────────────────────────────────────

class TestUploadAllOrchestration:
    def test_cartesian_product_2files_2accounts(self):
        inst = _make_platform()
        result, upload = _run_publish(
            inst,
            title='T', files=['/v1.mp4', '/v2.mp4'],
            account_file=['a.json', 'b.json'], desc='d',
        )
        assert result is True
        assert upload.await_count == 4
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['file_path'] == f'/v{i // 2 + 1}.mp4'
            assert call.kwargs['account_file'].endswith(f'{"ab"[i % 2]}.json')

    def test_single_file_single_account(self):
        inst = _make_platform()
        _, upload = _run_publish(inst, title='标题', files=['/v.mp4'], account_file=['a.json'])
        assert upload.await_count == 1
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['file_path'] == '/v.mp4'

    def test_param_passthrough(self):
        inst = _make_platform()
        _, upload = _run_publish(
            inst,
            title='标题', files=['/v.mp4'], tags=['t1'], account_file=['a.json'],
            thumbnail_landscape_path='/cover_l.png', thumbnail_portrait_path='/cover_p.png',
            video_format='mp4', desc='描述', author_statement='内容由AI生成',
            compilation='合集A', enableTimer=True, schedule_time_str='2026-08-21 10:00',
            reprint_url='https://example.com/src',
        )
        call = upload.await_args
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['thumbnail_landscape_path'] == '/cover_l.png'
        assert call.kwargs['thumbnail_portrait_path'] == '/cover_p.png'
        assert call.kwargs['video_format'] == 'mp4'
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['author_statement'] == '内容由AI生成'
        assert call.kwargs['compilation'] == '合集A'
        assert call.kwargs['enable_timer'] is True
        assert call.kwargs['schedule_time_str'] == '2026-08-21 10:00'
        assert call.kwargs['reprint_url'] == 'https://example.com/src'

    def test_cookie_path_resolution(self):
        inst = _make_platform()
        _, upload = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['u1.json'])
        assert upload.await_args.kwargs['account_file'] == str(Path(BASE_DIR / 'cookiesFile' / 'u1.json'))

    def test_strategy_immediate_log(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.alipay.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock()), \
             patch('impl.alipay.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.alipay.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json']))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('immediate',)
            for c in logger.info.call_args_list
        )

    def test_strategy_scheduled_log(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.alipay.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock()), \
             patch('impl.alipay.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.alipay.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(
                title='T', files=['/v.mp4'], account_file=['a.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('scheduled',)
            for c in logger.info.call_args_list
        )

    def test_enable_timer_without_time_is_immediate(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.alipay.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock()), \
             patch('impl.alipay.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.alipay.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json'], enableTimer=True))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('immediate',)
            for c in logger.info.call_args_list
        )

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        _, upload = _run_publish(inst, title='T')
        assert upload.await_count == 0

    def test_account_name_fallback_unknown(self):
        inst = _make_platform()
        with patch('impl.alipay.platform.get_account_name_by_cookie_file', return_value=''), \
             patch('impl.alipay.platform.bind_account_name', MagicMock()) as bind, \
             patch.object(inst, '_upload_one_video', AsyncMock()):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], account_file=['x.json']))
        bind.assert_called_once_with('-')
