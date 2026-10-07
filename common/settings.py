"""Typed configuration loaded from the rendered service_conf.yaml (D-28, SEC-04)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONF_PATH = "conf/service_conf.yaml"
MASK = "***"


class ConfigError(Exception):
    """Raised when a required configuration key is missing or malformed."""


@dataclass(frozen=True)
class MySQLSettings:
    name: str
    user: str
    password: str = field(repr=False)
    host: str
    port: int
    max_connections: int
    stale_timeout: int
    read_timeout: float = 30.0
    write_timeout: float = 30.0

    def __repr__(self) -> str:
        return f"MySQLSettings(name={self.name!r}, user={self.user!r}, password={MASK!r}, host={self.host!r}, port={self.port})"


@dataclass(frozen=True)
class RedisSettings:
    host: str
    port: int
    password: str = field(repr=False)
    db: int

    def __repr__(self) -> str:
        return f"RedisSettings(host={self.host!r}, port={self.port}, password={MASK!r}, db={self.db})"


@dataclass(frozen=True)
class MinioSettings:
    user: str
    password: str = field(repr=False)
    host: str
    port: int

    def __repr__(self) -> str:
        return f"MinioSettings(user={self.user!r}, password={MASK!r}, host={self.host!r}, port={self.port})"


@dataclass(frozen=True)
class EsSettings:
    hosts: str
    username: str
    password: str = field(repr=False)

    def __repr__(self) -> str:
        return f"EsSettings(hosts={self.hosts!r}, username={self.username!r}, password={MASK!r})"


@dataclass(frozen=True)
class CorsSettings:
    allowed_origins: tuple[str, ...]


@dataclass(frozen=True)
class LoggingSettings:
    dir: str
    level: str


@dataclass(frozen=True)
class ServerSettings:
    host: str
    http_port: int


MIN_SECRET_KEY_LENGTH = 32
TOKEN_MAX_AGE_SECONDS = 30 * 24 * 3600  # D-11
PASSWORD_ITERATIONS = 600000  # D-09
MAX_OTP_TTL_SECONDS = 3600
MAX_WINDOW_SECONDS = 86400
_PLACEHOLDER_KEYS = frozenset({"changeme", "secret", "change-me", "ragflow"})
_SMTP_SECURITY = ("none", "starttls", "tls")


@dataclass(frozen=True)
class SecuritySettings:
    secret_key: str = field(repr=False)
    token_max_age_seconds: int = TOKEN_MAX_AGE_SECONDS
    password_iterations: int = PASSWORD_ITERATIONS

    def __repr__(self) -> str:
        return f"SecuritySettings(secret_key={MASK!r}, token_max_age_seconds={self.token_max_age_seconds}, password_iterations={self.password_iterations})"

    __str__ = __repr__


@dataclass(frozen=True)
class AuthSettings:
    register_enabled: bool = True
    superuser_email: str = ""
    superuser_password: str = field(default="", repr=False)
    otp_ttl_seconds: int = 600

    def __repr__(self) -> str:
        return (
            f"AuthSettings(register_enabled={self.register_enabled}, superuser_email={self.superuser_email!r}, "
            f"superuser_password={MASK!r}, otp_ttl_seconds={self.otp_ttl_seconds})"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class MailSettings:
    host: str = "mailpit"
    port: int = 1025
    security: str = "none"
    username: str = ""
    password: str = field(default="", repr=False)
    sender: str = "no-reply@devrag.local"

    def __repr__(self) -> str:
        return (
            f"MailSettings(host={self.host!r}, port={self.port}, security={self.security!r}, "
            f"username={self.username!r}, password={MASK!r}, sender={self.sender!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class ModelsSettings:
    default_chat_model: str = ""
    default_embedding_model: str = ""
    default_rerank_model: str = ""
    default_factory: str = ""
    default_base_url: str = ""


@dataclass(frozen=True)
class RateLimitSettings:
    """Every rate-limit number (D-29). Defaults are the R-94 production values."""

    register_per_ip: int = 10
    register_window_seconds: int = 3600
    login_failures_per_email: int = 5
    login_per_ip: int = 30
    login_window_seconds: int = 900
    otp_email_interval_seconds: int = 60
    otp_per_email_per_hour: int = 5
    otp_per_ip_per_hour: int = 20
    otp_window_seconds: int = 3600


@dataclass(frozen=True)
class Settings:
    ragflow: ServerSettings
    mysql: MySQLSettings
    redis: RedisSettings
    minio: MinioSettings
    es: EsSettings
    cors: CorsSettings
    logging: LoggingSettings
    security: SecuritySettings
    auth: AuthSettings = field(default_factory=AuthSettings)
    mail: MailSettings = field(default_factory=MailSettings)
    models: ModelsSettings = field(default_factory=ModelsSettings)
    ratelimit: RateLimitSettings = field(default_factory=RateLimitSettings)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"missing required config section: {name}")
    return value


def _get(section: dict[str, Any], parent: str, key: str, cast: type = str) -> Any:
    if key not in section or section[key] is None or section[key] == "":
        raise ConfigError(f"missing required config key: {parent}.{key}")
    try:
        return cast(section[key])
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"invalid value for config key: {parent}.{key}") from exc


def _optional(section: dict[str, Any], key: str, default: str = "") -> str:
    value = section.get(key)
    return default if value is None or value == "" else str(value)


def _valid_secret_key(key: str) -> bool:
    return len(key) >= MIN_SECRET_KEY_LENGTH and key.lower() not in _PLACEHOLDER_KEYS and len(set(key)) > 1


def _bool(section: dict[str, Any], parent: str, key: str, default: bool) -> bool:
    raw = section.get(key)
    if raw is None or raw == "":
        return default
    text = str(raw).strip().lower()
    if text in ("1", "true"):
        return True
    if text in ("0", "false"):
        return False
    raise ConfigError(f"invalid value for config key: {parent}.{key}")


def _bounded(section: dict[str, Any], parent: str, key: str, default: int, hi: int | None = None) -> int:
    raw = section.get(key)
    if raw is None or raw == "":
        return default
    try:
        if isinstance(raw, bool):
            raise ValueError
        value = int(str(raw).strip())
    except ValueError as exc:
        raise ConfigError(f"invalid value for config key: {parent}.{key}") from exc
    if value < 1 or (hi is not None and value > hi):
        raise ConfigError(f"invalid value for config key: {parent}.{key}")
    return value


def _parse_security(data: dict[str, Any]) -> SecuritySettings:
    section = data.get("security")
    key = str(section.get("secret_key") or "").strip() if isinstance(section, dict) else ""
    if not _valid_secret_key(key):
        raise ConfigError(
            f"config key security.secret_key is missing, shorter than {MIN_SECRET_KEY_LENGTH} characters or a placeholder (run make init-env)"
        )
    return SecuritySettings(secret_key=key)


def _parse_auth(data: dict[str, Any]) -> AuthSettings:
    sec = data.get("auth") or {}
    return AuthSettings(
        register_enabled=_bool(sec, "auth", "register_enabled", True),
        superuser_email=_optional(sec, "superuser_email").strip(),
        superuser_password=_optional(sec, "superuser_password"),
        otp_ttl_seconds=_bounded(sec, "auth", "otp_ttl_seconds", 600, MAX_OTP_TTL_SECONDS),
    )


def _parse_mail(data: dict[str, Any]) -> MailSettings:
    sec = data.get("mail") or {}
    security = _optional(sec, "security", "none").strip()
    if security not in _SMTP_SECURITY:
        raise ConfigError("invalid value for config key: mail.security")
    defaults = MailSettings()
    return MailSettings(
        host=_optional(sec, "host", defaults.host),
        port=_bounded(sec, "mail", "port", defaults.port, 65535),
        security=security,
        username=_optional(sec, "username"),
        password=_optional(sec, "password"),
        sender=_optional(sec, "from", defaults.sender),
    )


def _parse_models(data: dict[str, Any]) -> ModelsSettings:
    sec = data.get("models") or {}
    return ModelsSettings(**{name: _optional(sec, name) for name in ModelsSettings.__dataclass_fields__})


def _parse_ratelimit(data: dict[str, Any]) -> RateLimitSettings:
    sec = data.get("ratelimit") or {}
    defaults = RateLimitSettings()
    values = {}
    for name in RateLimitSettings.__dataclass_fields__:
        hi = MAX_WINDOW_SECONDS if name.endswith(("_seconds",)) else None
        values[name] = _bounded(sec, "ratelimit", name, getattr(defaults, name), hi)
    return RateLimitSettings(**values)


def parse_settings(data: dict[str, Any]) -> Settings:
    if not isinstance(data, dict):
        raise ConfigError("configuration file is empty or not a mapping")
    srv, my, rd, mn, es = (_section(data, n) for n in ("ragflow", "mysql", "redis", "minio", "es"))
    cors = data.get("cors") or {}
    log = data.get("logging") or {}
    origins = tuple(o.strip() for o in _optional(cors, "allowed_origins").split(",") if o.strip())
    return Settings(
        ragflow=ServerSettings(_get(srv, "ragflow", "host"), _get(srv, "ragflow", "http_port", int)),
        mysql=MySQLSettings(
            name=_get(my, "mysql", "name"),
            user=_get(my, "mysql", "user"),
            password=_get(my, "mysql", "password"),
            host=_get(my, "mysql", "host"),
            port=_get(my, "mysql", "port", int),
            max_connections=_get(my, "mysql", "max_connections", int),
            stale_timeout=_get(my, "mysql", "stale_timeout", int),
            read_timeout=float(my.get("read_timeout") or 30),
            write_timeout=float(my.get("write_timeout") or 30),
        ),
        redis=RedisSettings(
            host=_get(rd, "redis", "host"),
            port=_get(rd, "redis", "port", int),
            password=_get(rd, "redis", "password"),
            db=int(rd.get("db", 0)),
        ),
        minio=MinioSettings(
            user=_get(mn, "minio", "user"),
            password=_get(mn, "minio", "password"),
            host=_get(mn, "minio", "host"),
            port=_get(mn, "minio", "port", int),
        ),
        es=EsSettings(
            hosts=_get(es, "es", "hosts"),
            username=_get(es, "es", "username"),
            password=_get(es, "es", "password"),
        ),
        cors=CorsSettings(allowed_origins=origins),
        logging=LoggingSettings(dir=_optional(log, "dir"), level=_optional(log, "level", "INFO").upper()),
        security=_parse_security(data),
        auth=_parse_auth(data),
        mail=_parse_mail(data),
        models=_parse_models(data),
        ratelimit=_parse_ratelimit(data),
    )


def load_settings(path: str | os.PathLike[str] | None = None) -> Settings:
    """Load settings from ``path``, ``$SERVICE_CONF`` or ``conf/service_conf.yaml``."""
    conf = Path(path or os.environ.get("SERVICE_CONF") or DEFAULT_CONF_PATH)
    try:
        raw = conf.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config file {conf}: {exc.strerror} (render it with scripts/render_conf.py)") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"config file {conf} is not valid YAML") from exc
    return parse_settings(data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
