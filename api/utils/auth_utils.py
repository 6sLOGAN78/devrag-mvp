import bcrypt
from datetime import datetime, timedelta

# In a real app this should come from config.CONF
JWT_SECRET = "devrag-super-secret-key-12345-long-enough-for-sha256"
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 24

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

