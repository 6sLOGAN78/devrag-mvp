from __future__ import annotations

import pytest

from common.constants import BUCKET_NAME, INDEX_PREFIX, NETWORK_NAME, SERVICE_NAME, RetCode
from common.settings import ConfigError, RateLimitSettings, load_settings
from scripts.render_conf import render
from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

FAKE_KEY = "fake-test-secret-key-0123456789abcdef-ZZ"
SECRETS = {"MYSQL_PASSWORD": "pw-mysql-123", "REDIS_PASSWORD": "pw-redis-123", "MINIO_PASSWORD": "pw-minio-123", "ELASTIC_PASSWORD": "pw-es-123", "SECRET_KEY": FAKE_KEY}


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


# --- Phase 2 sections: security, auth, mail, models, ratelimit (02-04, R-94, R-96, D-29) ---
import re  # noqa: E402

import yaml  # noqa: E402


def _with(conf, tmp_path, mutate):
    data = yaml.safe_load(conf.read_text())
    mutate(data)
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_phase2_sections_typed_defaults(conf):
    s = load_settings(conf)
    assert s.security.secret_key == FAKE_KEY
    assert s.security.token_max_age_seconds == 30 * 24 * 3600
    assert s.security.password_iterations == 600000
    assert s.auth.register_enabled is True
    assert s.auth.superuser_email == "" and s.auth.superuser_password == ""
    assert s.auth.otp_ttl_seconds == 600
    assert (s.mail.host, s.mail.port, s.mail.security, s.mail.sender) == ("mailpit", 1025, "none", "no-reply@devrag.local")
    assert s.models.default_chat_model == "" and s.models.default_factory == ""


def test_ratelimit_defaults_equal_r94_numbers(conf):
    assert load_settings(conf).ratelimit == RateLimitSettings(
        register_per_ip=10, register_window_seconds=3600, login_failures_per_email=5, login_per_ip=30,
        login_window_seconds=900, otp_email_interval_seconds=60, otp_per_email_per_hour=5,
        otp_per_ip_per_hour=20, otp_window_seconds=3600, provider_test_per_tenant=10, provider_test_window_seconds=300,
    )
    assert RateLimitSettings() == load_settings(conf).ratelimit


@pytest.mark.parametrize(
    "bad",
    ["", "fake-zq9-short", "x" * 31, "changeme", "secret", "change-me", "ragflow", "a" * 40, "CHANGEME", "0" * 64],
)
def test_bad_secret_key_rejected_without_echo(tmp_path, conf, bad):
    path = _with(conf, tmp_path, lambda d: d["security"].__setitem__("secret_key", bad))
    with pytest.raises(ConfigError, match=r"security\.secret_key") as err:
        load_settings(path)
    if bad in {"fake-zq9-short", "a" * 40}:
        assert bad not in str(err.value)


def test_missing_security_section_rejected(tmp_path, conf):
    path = _with(conf, tmp_path, lambda d: d.pop("security"))
    with pytest.raises(ConfigError, match="security"):
        load_settings(path)


@pytest.mark.parametrize(("raw", "expected"), [("1", True), ("0", False), ("true", True), ("false", False), ("TRUE", True), (True, True), (False, False)])
def test_register_enabled_parsing(tmp_path, conf, raw, expected):
    path = _with(conf, tmp_path, lambda d: d["auth"].__setitem__("register_enabled", raw))
    assert load_settings(path).auth.register_enabled is expected


@pytest.mark.parametrize("raw", ["t", "T", "f", "F", "yes", "no", "on", "2"])
def test_register_enabled_rejects_what_go_rejects(tmp_path, conf, raw):
    """IN-07: the accepted boolean set is identical in both engines."""
    path = _with(conf, tmp_path, lambda d: d["auth"].__setitem__("register_enabled", raw))
    with pytest.raises(ConfigError, match=r"auth\.register_enabled"):
        load_settings(path)


def test_register_enabled_invalid(tmp_path, conf):
    path = _with(conf, tmp_path, lambda d: d["auth"].__setitem__("register_enabled", "maybe"))
    with pytest.raises(ConfigError, match=r"auth\.register_enabled"):
        load_settings(path)


@pytest.mark.parametrize("ttl", [0, -1, 3601, "abc"])
def test_otp_ttl_bounds(tmp_path, conf, ttl):
    path = _with(conf, tmp_path, lambda d: d["auth"].__setitem__("otp_ttl_seconds", ttl))
    with pytest.raises(ConfigError, match=r"auth\.otp_ttl_seconds"):
        load_settings(path)


@pytest.mark.parametrize("ttl", [1, 3600])
def test_otp_ttl_bounds_accepted(tmp_path, conf, ttl):
    path = _with(conf, tmp_path, lambda d: d["auth"].__setitem__("otp_ttl_seconds", ttl))
    assert load_settings(path).auth.otp_ttl_seconds == ttl


def test_smtp_security_enum(tmp_path, conf):
    for ok in ("none", "starttls", "tls"):
        path = _with(conf, tmp_path, lambda d, ok=ok: d["mail"].__setitem__("security", ok))
        assert load_settings(path).mail.security == ok
    path = _with(conf, tmp_path, lambda d: d["mail"].__setitem__("security", "ssl3"))
    with pytest.raises(ConfigError, match=r"mail\.security"):
        load_settings(path)


@pytest.mark.parametrize("key", ["register_per_ip", "login_per_ip", "otp_per_email_per_hour"])
@pytest.mark.parametrize("value", [0, -5, "abc"])
def test_ratelimit_values_must_be_positive(tmp_path, conf, key, value):
    path = _with(conf, tmp_path, lambda d: d["ratelimit"].__setitem__(key, value))
    with pytest.raises(ConfigError, match=rf"ratelimit\.{key}"):
        load_settings(path)


@pytest.mark.parametrize("key", ["register_window_seconds", "login_window_seconds", "otp_window_seconds"])
def test_ratelimit_window_capped_at_one_day(tmp_path, conf, key):
    path = _with(conf, tmp_path, lambda d: d["ratelimit"].__setitem__(key, 86401))
    with pytest.raises(ConfigError, match=rf"ratelimit\.{key}"):
        load_settings(path)
    path = _with(conf, tmp_path, lambda d: d["ratelimit"].__setitem__(key, 86400))
    assert getattr(load_settings(path).ratelimit, key) == 86400


def test_repr_masks_secret_key_superuser_and_smtp_passwords(tmp_path, monkeypatch):
    values = {"SECRET_KEY": "fake-repr-secret-key-0123456789abcdef-QQ", "SUPERUSER_PASSWORD": "fake-su-pw-1", "SMTP_PASSWORD": "fake-smtp-pw-1"}
    text = render((REPO_ROOT / "conf/service_conf.yaml.template").read_text(), {**SECRETS, **values})
    path = tmp_path / "r.yaml"
    path.write_text(text)
    settings = load_settings(path)
    dumped = repr(settings) + str(settings) + repr(settings.security) + repr(settings.auth) + repr(settings.mail)
    for value in values.values():
        assert value not in dumped
    assert not re.search(r"fake-(repr|su|smtp)", dumped)
    assert "***" in dumped


# --- Phase 3 sections: llm, storage, upload and two rate-limit fields (03-01, D-11, D-13, D-23, D-28, SEC-03) ---
import base64  # noqa: E402
import dataclasses  # noqa: E402

BUILT_IN_EXTENSIONS = ("pdf", "docx", "pptx", "xlsx", "txt", "md", "markdown", "csv", "json", "html", "htm", "epub", "jpg", "jpeg", "png", "mp3", "wav")
FAKE_ENC_KEY = base64.urlsafe_b64encode(b"fake-llm-key-for-tests-0123456789"[:32].ljust(32, b"0")).decode()


def test_phase3_sections_typed_defaults(conf):
    s = load_settings(conf)
    assert s.llm.encryption_key == "" and s.llm.key_id == "k1"
    assert s.llm.allow_private_base_urls is False
    assert (s.llm.chat_timeout_seconds, s.llm.embedding_timeout_seconds, s.llm.key_test_timeout_seconds, s.llm.max_retries) == (60, 30, 20, 3)
    assert (s.storage.impl, s.storage.local_base_dir) == ("MINIO", "/ragflow/data/storage")
    assert s.upload.max_file_bytes == 104857600
    assert s.upload.max_files_per_request == 20
    assert s.upload.max_documents_per_dataset == 10000
    assert s.upload.body_timeout_seconds == 600
    assert s.upload.allowed_extensions == BUILT_IN_EXTENSIONS
    assert (s.ratelimit.provider_test_per_tenant, s.ratelimit.provider_test_window_seconds) == (10, 300)


def test_built_in_extensions_exclude_unsupported_image_types():
    for gone in ("gif", "bmp", "tiff", "webp"):
        assert gone not in BUILT_IN_EXTENSIONS


def test_old_settings_construction_still_works(conf):
    s = load_settings(conf)
    required = {f.name: getattr(s, f.name) for f in dataclasses.fields(s) if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING}
    from common.settings import Settings

    rebuilt = Settings(**required)
    assert rebuilt.llm.encryption_key == "" and rebuilt.upload.max_files_per_request == 20 and rebuilt.storage.impl == "MINIO"


def test_llm_repr_and_str_never_contain_the_key(tmp_path, conf):
    path = _with(conf, tmp_path, lambda d: d["llm"].__setitem__("encryption_key", FAKE_ENC_KEY))
    settings = load_settings(path)
    assert settings.llm.encryption_key == FAKE_ENC_KEY
    dumped = repr(settings) + str(settings) + repr(settings.llm) + str(settings.llm)
    assert FAKE_ENC_KEY not in dumped
    assert "***" in dumped


@pytest.mark.parametrize("bad", ["not base64 !!", "short", base64.urlsafe_b64encode(b"x" * 31).decode(), base64.urlsafe_b64encode(b"x" * 33).decode(), "a" * 43 + "$"])
def test_bad_encryption_key_rejected_without_echo(tmp_path, conf, bad):
    path = _with(conf, tmp_path, lambda d: d["llm"].__setitem__("encryption_key", bad))
    with pytest.raises(ConfigError, match=r"llm\.encryption_key") as err:
        load_settings(path)
    assert bad not in str(err.value)


def test_empty_encryption_key_parses(tmp_path, conf):
    path = _with(conf, tmp_path, lambda d: d["llm"].__setitem__("encryption_key", ""))
    assert load_settings(path).llm.encryption_key == ""


@pytest.mark.parametrize(("key", "value"), [("max_file_bytes", 104857601), ("max_file_bytes", 0), ("max_files_per_request", 101), ("max_files_per_request", 0), ("max_documents_per_dataset", 1000001), ("max_documents_per_dataset", "abc")])
def test_upload_bounds(tmp_path, conf, key, value):
    path = _with(conf, tmp_path, lambda d: d["upload"].__setitem__(key, value))
    with pytest.raises(ConfigError, match=rf"upload\.{key}"):
        load_settings(path)


def test_upload_max_file_bytes_upper_bound_is_accepted(tmp_path, conf):
    path = _with(conf, tmp_path, lambda d: d["upload"].__setitem__("max_file_bytes", 104857600))
    assert load_settings(path).upload.max_file_bytes == 104857600


@pytest.mark.parametrize(("value", "expected"), [("", BUILT_IN_EXTENSIONS), ("PDF, Md ,txt", ("pdf", "md", "txt"))])
def test_allowed_extensions_parsing(tmp_path, conf, value, expected):
    path = _with(conf, tmp_path, lambda d: d["upload"].__setitem__("allowed_extensions", value))
    assert load_settings(path).upload.allowed_extensions == expected


@pytest.mark.parametrize("bad", ["pdf,.md", "pdf,a b", "pdf,toolongextension", "pdf;txt"])
def test_allowed_extensions_rejects_malformed_entries(tmp_path, conf, bad):
    path = _with(conf, tmp_path, lambda d: d["upload"].__setitem__("allowed_extensions", bad))
    with pytest.raises(ConfigError, match=r"upload\.allowed_extensions"):
        load_settings(path)


@pytest.mark.parametrize("impl", ["MINIO", "LOCAL"])
def test_storage_impl_accepts_minio_and_local(tmp_path, conf, impl):
    path = _with(conf, tmp_path, lambda d: d["storage"].__setitem__("impl", impl))
    assert load_settings(path).storage.impl == impl


@pytest.mark.parametrize("impl", ["S3", "AZURE", "minio2"])
def test_storage_impl_rejects_other_values(tmp_path, conf, impl):
    path = _with(conf, tmp_path, lambda d: d["storage"].__setitem__("impl", impl))
    with pytest.raises(ConfigError, match=r"storage\.impl"):
        load_settings(path)


@pytest.mark.parametrize(("key", "value"), [("max_retries", 6), ("chat_timeout_seconds", 0), ("key_test_timeout_seconds", "abc")])
def test_llm_numeric_bounds(tmp_path, conf, key, value):
    path = _with(conf, tmp_path, lambda d: d["llm"].__setitem__(key, value))
    with pytest.raises(ConfigError, match=rf"llm\.{key}"):
        load_settings(path)


def test_llm_zero_retries_is_allowed(tmp_path, conf):
    path = _with(conf, tmp_path, lambda d: d["llm"].__setitem__("max_retries", 0))
    assert load_settings(path).llm.max_retries == 0
