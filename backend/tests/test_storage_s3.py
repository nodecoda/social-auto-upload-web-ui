"""S3Storage 后端测试：mock boto3.client，验证参数传递与边界行为。"""
from unittest.mock import MagicMock

import boto3
import pytest

from storage.s3 import S3Storage


@pytest.fixture()
def s3(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(boto3, 'client', MagicMock(return_value=client))
    return S3Storage('http://minio:9000', 'ak', 'sk', 'my-bucket', region='cn-1'), client


def test_constructor_passes_credentials_and_config(s3, monkeypatch):
    storage, _ = s3
    boto3.client.assert_called_once()
    kwargs = boto3.client.call_args.kwargs
    assert kwargs['endpoint_url'] == 'http://minio:9000'
    assert kwargs['aws_access_key_id'] == 'ak'
    assert kwargs['aws_secret_access_key'] == 'sk'
    assert kwargs['region_name'] == 'cn-1'
    assert storage.bucket == 'my-bucket'


def test_save_uploads_fileobj_and_returns_path(s3):
    storage, client = s3
    assert storage.save(b'data', 'dir/f.mp4') == 'dir/f.mp4'
    assert client.upload_fileobj.call_count == 1
    args = client.upload_fileobj.call_args.args
    assert args[0].read() == b'data'   # BytesIO 包装
    assert args[1] == 'my-bucket'
    assert args[2] == 'dir/f.mp4'
    assert 'Config' in client.upload_fileobj.call_args.kwargs


def test_save_stream_wraps_iterator_as_filelike(s3):
    storage, client = s3
    assert storage.save_stream(iter([b'a', b'b', b'c']), 's.bin') == 's.bin'
    assert client.upload_fileobj.call_count == 1
    wrapped = client.upload_fileobj.call_args.args[0]
    assert wrapped.read() == b'abc'    # 一次性读
    assert wrapped.read(1) == b''      # 耗尽后返回空


def test_get_reads_body(s3):
    storage, client = s3
    client.get_object.return_value = {'Body': MagicMock(read=MagicMock(return_value=b'payload'))}
    assert storage.get('k.txt') == b'payload'
    client.get_object.assert_called_once_with(Bucket='my-bucket', Key='k.txt')


def test_get_url_uses_presigned(s3):
    storage, client = s3
    client.generate_presigned_url.return_value = 'https://presigned/url'
    assert storage.get_url('k.txt') == 'https://presigned/url'
    client.generate_presigned_url.assert_called_once_with(
        'get_object', Params={'Bucket': 'my-bucket', 'Key': 'k.txt'}, ExpiresIn=3600
    )


def test_delete_calls_delete_object(s3):
    storage, client = s3
    assert storage.delete('k.txt') is True
    client.delete_object.assert_called_once_with(Bucket='my-bucket', Key='k.txt')


def test_exists_head_object(s3):
    storage, client = s3
    client.head_object.return_value = {}
    assert storage.exists('k.txt') is True
    client.head_object.side_effect = Exception('NoSuchKey')
    assert storage.exists('k.txt') is False


def test_get_local_path_local_fallback_first(s3, tmp_path):
    storage, _ = s3
    storage.base_dir = tmp_path
    (tmp_path / 'legacy.txt').write_bytes(b'x')
    assert storage.get_local_path('legacy.txt') == str(tmp_path / 'legacy.txt')
    # 本地不存在 → 尝试下载（mock get）
    storage.get = MagicMock(return_value=b'remote')
    p = storage.get_local_path('remote.txt')
    assert p and p.endswith('.txt')
    with open(p, 'rb') as f:
        assert f.read() == b'remote'


def test_get_local_path_download_failure_returns_none(s3):
    storage, _ = s3
    storage.base_dir = None
    storage.get = MagicMock(side_effect=Exception('network down'))
    assert storage.get_local_path('k.txt') is None


def test_serve_redirects_to_presigned_url(s3):
    storage, client = s3
    client.generate_presigned_url.return_value = 'https://presigned/x'
    resp = storage.serve('k.txt')
    assert resp.status_code == 302
    assert resp.headers['Location'] == 'https://presigned/x'
