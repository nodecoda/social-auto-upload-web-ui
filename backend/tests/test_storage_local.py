"""LocalStorage 文件系统后端全量测试（覆盖 save/get/delete/exists/serve 等）。"""
import pytest
from werkzeug.exceptions import NotFound

from app import app as flask_app
from storage.local import LocalStorage


@pytest.fixture()
def storage(tmp_path):
    return LocalStorage(str(tmp_path / 'base'))


def test_save_writes_bytes_and_creates_parent_dirs(storage, tmp_path):
    rel = storage.save(b'hello world', 'videos/2026/a.mp4')
    assert rel == 'videos/2026/a.mp4'
    assert (tmp_path / 'base' / rel).read_bytes() == b'hello world'


def test_save_stream_joins_chunks(storage, tmp_path):
    rel = storage.save_stream(iter([b'chunk1', b'chunk2', b'' ]), 'streams/b.bin')
    assert (tmp_path / 'base' / rel).read_bytes() == b'chunk1chunk2'


def test_get_returns_bytes(storage, tmp_path):
    storage.save(b'data-123', 'c.txt')
    assert storage.get('c.txt') == b'data-123'


def test_get_url_format(storage):
    assert storage.get_url('d/e.mp4') == '/api/materials/file/d/e.mp4'


def test_delete_existing_file(storage, tmp_path):
    storage.save(b'x', 'gone.txt')
    assert storage.delete('gone.txt') is True
    assert not (tmp_path / 'base' / 'gone.txt').exists()


def test_delete_missing_file_returns_false(storage):
    assert storage.delete('nope.txt') is False


def test_exists(storage, tmp_path):
    storage.save(b'x', 'yes.txt')
    assert storage.exists('yes.txt') is True
    assert storage.exists('no.txt') is False


def test_get_local_path(storage, tmp_path):
    storage.save(b'x', 'local.txt')
    assert storage.get_local_path('local.txt') == str(tmp_path / 'base' / 'local.txt')
    assert storage.get_local_path('missing.txt') is None


def test_serve_returns_file(storage, tmp_path):
    storage.save(b'file-body', 'serve/me.txt')
    # send_from_directory 是 direct passthrough 响应：遍历底层迭代器读取内容
    with flask_app.test_request_context():
        resp = storage.serve('serve/me.txt')
        assert resp.status_code == 200
        assert b''.join(resp.response) == b'file-body'


def test_serve_missing_file_404(storage):
    # send_from_directory 对缺失文件抛 werkzeug NotFound（生产环境由 Flask 转 404）
    with flask_app.test_request_context(), pytest.raises(NotFound):
        storage.serve('absent.txt')
