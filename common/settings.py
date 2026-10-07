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


@dataclass(frozen=True)
class Settings:
    ragflow: ServerSettings
    mysql: MySQLSettings
    redis: RedisSettings
    minio: MinioSettings
    es: EsSettings
    cors: CorsSettings
    logging: LoggingSettings


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
