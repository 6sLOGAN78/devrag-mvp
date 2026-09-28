import redis
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.config import CONF

redis_conf = CONF['redis']
REDIS_CLIENT = redis.Redis.from_url(redis_conf['url'], decode_responses=True)

try:
    REDIS_CLIENT.ping()
    print("Redis connected successfully (Python).")
except Exception as e:
    raise RuntimeError(f"Failed to connect to Redis: {e}")
