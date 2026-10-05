"""Create the object-storage bucket if absent: ``python -m common.bootstrap.ensure_bucket`` (idempotent)."""
from __future__ import annotations

import logging
import sys

import urllib3
from minio import Minio
from minio.error import S3Error

from common.constants import BUCKET_NAME
from common.log_utils import init_root_logger
from common.settings import ConfigError, Settings, get_settings

logger = logging.getLogger("ensure_bucket")


def ensure_bucket(settings: Settings, bucket: str = BUCKET_NAME) -> bool:
    """Create ``bucket`` when missing. Returns True when it was created."""
    mn = settings.minio
    http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=10), retries=urllib3.Retry(total=2, backoff_factor=0.5))
    try:
        client = Minio(f"{mn.host}:{mn.port}", access_key=mn.user, secret_key=mn.password, secure=False, http_client=http)
        if client.bucket_exists(bucket):
            return False
        try:
            client.make_bucket(bucket)
        except S3Error as exc:
            if exc.code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):  # lost a creation race
                return False
            raise
        return True
    finally:
        http.clear()


def main() -> int:
    init_root_logger("ensure_bucket")
    try:
        created = ensure_bucket(get_settings())
    except ConfigError as exc:
        logger.error("configuration error: %s", exc)
        return 1
    except Exception:
        logger.exception("bucket bootstrap failed")
        return 1
    logger.info("bucket ready", extra={"bucket": BUCKET_NAME, "bucket_created": created})
    return 0


if __name__ == "__main__":
    sys.exit(main())
