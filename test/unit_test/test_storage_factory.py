"""Storage factory (plan 03-07, STOR-01)."""
from __future__ import annotations

from dataclasses import replace

import pytest
from rag.utils.local_conn import LocalStorage
from rag.utils.storage_factory import get_storage, reset_storage_cache

from common.settings import ConfigError, MinioSettings, Settings, StorageSettings, load_settings
from scripts.render_conf import render
from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

SECRETS = {
    "MYSQL_PASSWORD": "pw-mysql-123",
    "REDIS_PASSWORD": "pw-redis-123",
    "MINIO_PASSWORD": "pw-minio-123",
    "ELASTIC_PASSWORD": "pw-es-123",
    "SECRET_KEY": "fake-test-secret-key-0123456789abcdef-ZZ",
}


@pytest.fixture(autouse=True)
def _fresh_cache():
    reset_storage_cache()
    yield
    reset_storage_cache()


@pytest.fixture
def base_settings(tmp_path) -> Settings:
    path = tmp_path / "service_conf.yaml"
    path.write_text(render((REPO_ROOT / "conf/service_conf.yaml.template").read_text(), SECRETS))
    return load_settings(path)


def with_storage(settings: Settings, **kwargs) -> Settings:
    return replace(settings, storage=StorageSettings(**kwargs))


def test_default_impl_is_minio(base_settings):
    assert base_settings.storage.impl == "MINIO"


def test_minio_impl_returns_the_minio_driver(base_settings):
    from rag.utils.minio_conn import MinioStorage

    storage = get_storage(with_storage(base_settings, impl="MINIO"))
    assert isinstance(storage, MinioStorage)


def test_minio_impl_is_cached(base_settings):
    settings = with_storage(base_settings, impl="MINIO")
    assert get_storage(settings) is get_storage(settings)


def test_minio_endpoint_change_builds_a_new_driver(base_settings):
    first = get_storage(base_settings)
    moved = replace(base_settings, minio=MinioSettings(user="u", password="p", host="other-host", port=9000))
    assert get_storage(moved) is not first


def test_local_impl_uses_local_base_dir(base_settings, tmp_path):
    storage = get_storage(with_storage(base_settings, impl="LOCAL", local_base_dir=str(tmp_path / "store")))
    assert isinstance(storage, LocalStorage)
    storage.put("ragflow", "0123456789abcdef0123456789abcdef/ffffffffffffffffffffffffffffffff", b"x")
    assert (tmp_path / "store" / "ragflow").is_dir()


def test_local_impl_is_cached_per_base_dir(base_settings, tmp_path):
    a = with_storage(base_settings, impl="LOCAL", local_base_dir=str(tmp_path / "a"))
    b = with_storage(base_settings, impl="LOCAL", local_base_dir=str(tmp_path / "b"))
    assert get_storage(a) is get_storage(a)
    assert get_storage(a) is not get_storage(b)


@pytest.mark.parametrize("impl", ["S3", "", "minio", "local", "AZURE"])
def test_unknown_impl_names_the_config_key(base_settings, impl):
    with pytest.raises(ConfigError, match=r"storage\.impl"):
        get_storage(with_storage(base_settings, impl=impl))
