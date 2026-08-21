"""微博 publish_video / publish_image 编排层契约测试（T16b）。

publish_video(sync wrapper) → _upload_all: 文件×账号笛卡尔积, 169/916 封面 +
category/内容声明/合集透传, 策略固定 immediate。
publish_image(sync wrapper) → _upload_all_images: 单层账号循环(非笛卡尔积),
图集 >18 张硬上限校验, dry_run 早返回。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.weibo.platform import WeiboPlatform


def _make_platform():
    return WeiboPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_one_video / 账号名 运行 publish_video,返回 (result, upload)。"""
    upload = AsyncMock()
    with patch.object(platform, '_upload_one_video', upload), \
         patch('impl.weibo.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.weibo.platform.bind_account_name', MagicMock()):
        result = asyncio.run(platform.publish_video(**kwargs))
    return result, upload


def _run_publish_image(platform, **kwargs):
    """以 mock _upload_one_image / 账号名 运行 publish_image,返回 (result, upload)。"""
    upload = AsyncMock()
    with patch.object(platform, '_upload_one_image', upload), \
         patch('impl.weibo.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.weibo.platform.bind_account_name', MagicMock()):
        result = platform.publish_image(**kwargs)
    return result, upload


# ── publish_video sync wrapper ──────────────────────────────────────────────

class TestPublishVideoSync:
    def test_returns_true_and_calls_upload_all(self):
        inst = _make_platform()
        with patch.object(inst, '_upload_all', AsyncMock()) as upload_all:
            assert asyncio.run(inst.publish_video(title='T', files=['/v.mp4'])) is True
            upload_all.assert_awaited_once()


# ── _upload_all 视频编排 ────────────────────────────────────────────────────

class TestUploadAllVideo:
    def test_cartesian_product_2files_2accounts(self):
        inst = _make_platform()
        result, upload = _run_publish(
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
        _, upload = _run_publish(
            inst,
            title='标题', files=['/v.mp4'], tags=['t1'], account_file=['a.json'],
            thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
            thumbnail_landscape_169_path='/l169.png', thumbnail_portrait_916_path='/p916.png',
            desc='描述', category=['channel', 'sub'], ai_content='原创',
            content_statement='内容声明', content_statement2='声明2',
            content_statement2_optional='可选', weibo_collection='合集A',
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['tags'] == ['t1']
        assert call.kwargs['thumbnail_landscape_path'] == '/l.png'
        assert call.kwargs['thumbnail_portrait_path'] == '/p.png'
        assert call.kwargs['thumbnail_landscape_169_path'] == '/l169.png'
        assert call.kwargs['thumbnail_portrait_916_path'] == '/p916.png'
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['category'] == ['channel', 'sub']
        assert call.kwargs['ai_content'] == '原创'
        assert call.kwargs['content_statement'] == '内容声明'
        assert call.kwargs['content_statement2'] == '声明2'
        assert call.kwargs['content_statement2_optional'] == '可选'
        assert call.kwargs['weibo_collection'] == '合集A'

    def test_cookie_path_resolution(self):
        inst = _make_platform()
        _, upload = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['u1.json'])
        assert upload.await_args.kwargs['account_file'] == str(Path(BASE_DIR / 'cookiesFile' / 'u1.json'))

    def test_strategy_always_immediate_log(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch.object(inst, '_upload_one_video', AsyncMock()), \
             patch('impl.weibo.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.weibo.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json']))
        assert any(
            c.args[0] == '[发布策略] 发布策略: immediate'
            for c in logger.info.call_args_list
        )

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        _, upload = _run_publish(inst, title='T')
        assert upload.await_count == 0


# ── publish_image 图集 ──────────────────────────────────────────────────────

class TestPublishImage:
    def test_dry_run_returns_early(self):
        inst = _make_platform()
        with patch.object(inst, '_upload_all_images', AsyncMock()) as upload_all:
            assert inst.publish_image(files=['/i1.png'], dry_run=True) is True
            upload_all.assert_not_awaited()

    def test_normal_path_calls_upload_all_images(self):
        inst = _make_platform()
        with patch.object(inst, '_upload_all_images', AsyncMock()) as upload_all:
            assert inst.publish_image(files=['/i1.png']) is True
            upload_all.assert_awaited_once()

    def test_over_18_images_raises(self):
        inst = _make_platform()
        files = [f'/i{i}.png' for i in range(19)]
        with pytest.raises(ValueError, match="最多 18 张"):
            _run_publish_image(inst, files=files, account_file=['a.json'])

    def test_exactly_18_images_ok(self):
        inst = _make_platform()
        files = [f'/i{i}.png' for i in range(18)]
        result, upload = _run_publish_image(inst, files=files, account_file=['a.json'])
        assert result is True
        assert upload.await_count == 1

    def test_single_account_loop_not_cartesian(self):
        """图集是单层账号循环:1 账号 × 3 图 → _upload_one_image 只调 1 次,带全量图。"""
        inst = _make_platform()
        _, upload = _run_publish_image(
            inst, title='图集', files=['/i1.png', '/i2.png', '/i3.png'],
            account_file=['a.json'], desc='d', ai_content='原创',
            content_statement='声明', content_statement2='声明2',
            content_statement2_optional='可选',
        )
        assert upload.await_count == 1
        call = upload.await_args
        assert call.kwargs['file_path_list'] == ['/i1.png', '/i2.png', '/i3.png']
        assert call.kwargs['title'] == '图集'
        assert call.kwargs['desc'] == 'd'
        assert call.kwargs['ai_content'] == '原创'
        assert call.kwargs['content_statement'] == '声明'
        assert call.kwargs['content_statement2'] == '声明2'
        assert call.kwargs['content_statement2_optional'] == '可选'
        assert call.kwargs['account_file'] == str(Path(BASE_DIR / 'cookiesFile' / 'a.json'))

    def test_multi_account_loop_calls_per_account(self):
        inst = _make_platform()
        _, upload = _run_publish_image(
            inst, files=['/i1.png', '/i2.png'], account_file=['a.json', 'b.json'],
        )
        assert upload.await_count == 2
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['account_file'].endswith(f'{"ab"[i]}.json')
            # 每个账号都收到全量图
            assert call.kwargs['file_path_list'] == ['/i1.png', '/i2.png']
