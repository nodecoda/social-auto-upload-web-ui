"""image_service + storage 存储路由小面补测（T14）。

image_service: PIL 读图头识别尺寸(文件缺失/PIL 缺失/异常/正常)。
storage: 配置读取 / get_storage 分派 / get_storage_by_type 四分支 /
resolve_material_path 兜底。
"""
import sys
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from services.image_service import get_image_dimensions
from storage import _read_storage_config, get_storage, get_storage_by_type, reset_storage, resolve_material_path

# ── image_service ──────────────────────────────────────────────────────────

class TestImageDimensions:
    def test_file_missing(self):
        assert get_image_dimensions('/nonexistent/x.jpg') == (0, 0)

    def test_pil_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'PIL', None)
        assert get_image_dimensions('/x.jpg') == (0, 0)

    def test_success(self, tmp_path):
        img = tmp_path / 'a.png'
        img.write_bytes(b'png')
        fake_img = MagicMock()
        fake_img.size = (800, 600)
        fake_img.__enter__.return_value = fake_img  # with Image.open(...) as img
        with patch('PIL.Image.open', return_value=fake_img) as m:
            assert get_image_dimensions(str(img)) == (800, 600)
        m.assert_called_once_with(Path(str(img)))

    def test_open_exception(self, tmp_path):
        img = tmp_path / 'broken.png'
        img.write_bytes(b'bad')
        with patch('PIL.Image.open', side_effect=RuntimeError('corrupt')):
            assert get_image_dimensions(str(img)) == (0, 0)


# ── storage: 配置读取 ───────────────────────────────────────────────────────

class TestReadStorageConfig:
    def test_dict(self):
        with patch('impl.settings.get_storage_config',
                   return_value={'type': 's3', 's3': {'endpoint': 'https://s3'}}):
            assert _read_storage_config() == ('s3', {'endpoint': 'https://s3'})

    def test_non_dict_fallback(self):
        with patch('impl.settings.get_storage_config', return_value="type=local"):
            assert _read_storage_config() == ('local', {})


# ── storage: get_storage 分派 ──────────────────────────────────────────────

class TestGetStorage:
    def test_s3_with_endpoint(self):
        cfg = {'type': 's3', 's3': {'endpoint': 'https://s3.example.com', 'bucket': 'b'}}
        with patch('storage._read_storage_config', return_value=('s3', cfg['s3'])), \
             patch('storage.s3.S3Storage') as s3:
            s3.return_value = 's3-instance'
            assert get_storage() == 's3-instance'
            s3.assert_called_once_with(
                endpoint='https://s3.example.com', access_key='', secret_key='',
                bucket='b', region='', base_dir=ANY)

    def test_s3_missing_endpoint_falls_local(self):
        with patch('storage._read_storage_config', return_value=('s3', {})), \
             patch('storage.local.LocalStorage') as local:
            local.return_value = 'local-instance'
            assert get_storage() == 'local-instance'

    def test_local(self):
        with patch('storage._read_storage_config', return_value=('local', {})), \
             patch('storage.local.LocalStorage') as local:
            local.return_value = 'local-instance'
            assert get_storage() == 'local-instance'


# ── storage: get_storage_by_type ───────────────────────────────────────────

class TestGetStorageByType:
    def test_s3_when_global_s3(self):
        fake = MagicMock()
        fake.type = 's3'
        with patch('storage.get_storage', return_value=fake):
            assert get_storage_by_type('s3') == fake

    def test_s3_global_local_but_config_has_endpoint(self):
        local_storage = MagicMock()
        local_storage.type = 'local'
        with patch('storage.get_storage', return_value=local_storage), \
             patch('storage._read_storage_config',
                   return_value=('local', {'endpoint': 'https://s3.example.com'})), \
             patch('storage.s3.S3Storage') as s3:
            s3.return_value = 's3-fallback'
            assert get_storage_by_type('s3') == 's3-fallback'

    def test_s3_no_endpoint_falls_local(self):
        local_storage = MagicMock()
        local_storage.type = 'local'
        with patch('storage.get_storage', return_value=local_storage), \
             patch('storage._read_storage_config', return_value=('local', {})), \
             patch('storage.local.LocalStorage') as local:
            local.return_value = 'local-instance'
            assert get_storage_by_type('s3') == 'local-instance'

    def test_local_type(self):
        with patch('storage.local.LocalStorage') as local:
            local.return_value = 'local-instance'
            assert get_storage_by_type('local') == 'local-instance'

    def test_unknown_type_local(self):
        with patch('storage.local.LocalStorage') as local:
            local.return_value = 'local-instance'
            assert get_storage_by_type('ftp') == 'local-instance'


# ── storage: resolve_material_path ─────────────────────────────────────────

class TestResolveMaterialPath:
    def test_empty(self):
        assert resolve_material_path('') == ''
        assert resolve_material_path(None) is None

    def test_local_resolved(self):
        with patch('storage.get_storage') as gs:
            gs.return_value.get_local_path.return_value = '/abs/path.mp4'
            assert resolve_material_path('materials/a.mp4') == '/abs/path.mp4'

    def test_fallback_raw(self):
        with patch('storage.get_storage') as gs:
            gs.return_value.get_local_path.return_value = None
            assert resolve_material_path('raw/path.mp4') == 'raw/path.mp4'


class TestResetStorage:
    def test_noop(self):
        assert reset_storage() is None
