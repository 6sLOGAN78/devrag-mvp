from __future__ import annotations

import pytest

from common.constants import BUCKET_NAME, INDEX_PREFIX, NETWORK_NAME, SERVICE_NAME, RetCode
from common.settings import ConfigError, load_settings
from scripts.render_conf import render
from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

SECRETS = {"MYSQL_PASSWORD": "pw-mysql-123", "REDIS_PASSWORD": "pw-redis-123", "MINIO_PASSWORD": "pw-minio-123", "ELASTIC_PASSWORD": "pw-es-123"}


@pytest.fixture
def conf(tmp_path):
    text = render((REPO_ROOT / "conf/service_conf.yaml.template").read_text(), SECRETS)
    path = tmp_path / "service_conf.yaml"
    path.write_text(text)
    return path


def test_load_typed_sections(conf):
    s = load_settings(conf)
    assert s.mysql.host == "mysql" and s.mysql.port == 3306 and s.mysql.max_connections == 100
    assert s.redis.port == 6379 and s.minio.port == 9000
    assert s.es.hosts == "http://es01:9200"
    assert s.cors.allowed_origins == ()
    assert s.logging.level == "INFO"
    assert s.ragflow.http_port == 9380


def test_missing_key_names_dotted_path(tmp_path, conf):
    broken = conf.read_text().replace("  user: 'ragflow_app'\n", "")
    path = tmp_path / "b.yaml"
    path.write_text(broken)
    with pytest.raises(ConfigError, match=r"mysql\.user"):
        load_settings(path)


def test_missing_file_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="cannot read config file"):
        load_settings(tmp_path / "nope.yaml")


def test_repr_masks_every_secret(conf):
    text = repr(load_settings(conf))
    for value in SECRETS.values():
        assert value not in text
    assert "***" in text


def test_cors_origins_split(tmp_path, conf):
    path = tmp_path / "c.yaml"
    path.write_text(conf.read_text().replace("allowed_origins: ''", "allowed_origins: 'http://a.test, http://b.test'"))
    assert load_settings(path).cors.allowed_origins == ("http://a.test", "http://b.test")


def test_identifier_constants():
    assert (SERVICE_NAME, INDEX_PREFIX, BUCKET_NAME, NETWORK_NAME) == ("ragflow_server", "ragflow_", "ragflow", "ragflow")


@pytest.mark.parametrize(
    ("name", "value"),
    [("SUCCESS", 0), ("NOT_EFFECTIVE", 10), ("EXCEPTION_ERROR", 100), ("ARGUMENT_ERROR", 101), ("DATA_ERROR", 102), ("OPERATING_ERROR", 103),
     ("CONNECTION_ERROR", 105), ("RUNNING", 106), ("PERMISSION_ERROR", 108), ("AUTHENTICATION_ERROR", 109), ("BAD_REQUEST", 400),
     ("UNAUTHORIZED", 401), ("FORBIDDEN", 403), ("NOT_FOUND", 404), ("METHOD_NOT_ALLOWED", 405), ("CONFLICT", 409),
     ("SERVER_ERROR", 500), ("SERVICE_UNAVAILABLE", 503)],
)
def test_retcode_values(name, value):
    assert RetCode[name] == value
