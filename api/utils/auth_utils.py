import bcrypt
import jwt
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

def generate_jwt(user_id: str, tenant_id: str) -> str:
    """Generate a JWT containing user_id and tenant_id."""
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt(token: str) -> dict:
    """Decode and verify a JWT."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
