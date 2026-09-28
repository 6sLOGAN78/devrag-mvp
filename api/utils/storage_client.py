from minio import Minio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.config import CONF

minio_conf = CONF['minio']
# Endpoint usually comes as 127.0.0.1:9000
STORAGE_CLIENT = Minio(
    minio_conf['endpoint'],
    access_key=minio_conf['user'],
    secret_key=minio_conf['password'],
    secure=False # CRITICAL: MinIO local runs without HTTPS
)

try:
    STORAGE_CLIENT.list_buckets()
    print("MinIO connected successfully and authenticated (Python).")
except Exception as e:
    raise RuntimeError(f"Failed to connect to MinIO: {e}")
