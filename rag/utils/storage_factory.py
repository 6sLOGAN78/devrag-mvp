"""Select the storage driver from ``settings.storage.impl`` (plan 03-07, STOR-01).

``MINIO`` (default) and ``LOCAL`` are the only implementations; anything else is a configuration error. Drivers are cached per
(impl, local base dir, MinIO endpoint) so every caller shares one connection pool.
"""
from __future__ import annotations

import threading

from common.settings import ConfigError, Settings
from rag.utils.storage_base import Storage

_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str, str], Storage] = {}


def get_storage(settings: Settings) -> Storage:
    impl = settings.storage.impl
    if impl == "MINIO":
        cache_key = (impl, "", f"{settings.minio.host}:{settings.minio.port}/{settings.minio.user}")
    elif impl == "LOCAL":
        cache_key = (impl, settings.storage.local_base_dir, "")
    else:
        raise ConfigError("invalid value for config key: storage.impl")
    with _LOCK:
        cached = _CACHE.get(cache_key)
        if cached is None:
            if impl == "MINIO":
                from rag.utils.minio_conn import MinioStorage  # lazy: keeps the minio SDK out of LOCAL deployments

                cached = MinioStorage(settings)
            else:
                from rag.utils.local_conn import LocalStorage

                cached = LocalStorage(settings.storage.local_base_dir)
            _CACHE[cache_key] = cached
        return cached


def reset_storage_cache() -> None:
    """Drop cached drivers (tests and settings reloads)."""
    with _LOCK:
        _CACHE.clear()
