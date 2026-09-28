from api.utils.auth_utils import hash_password, verify_password, generate_jwt, decode_jwt
import sys

def test_auth():
    # 1. Test Password Hashing
    password = "MySecurePassword123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) == True
    assert verify_password("WrongPassword", hashed) == False

    # 2. Test JWT
    user_id = "user_1"
    tenant_id = "tenant_1"
    token = generate_jwt(user_id, tenant_id)
    decoded = decode_jwt(token)
    assert decoded["user_id"] == user_id
    assert decoded["tenant_id"] == tenant_id
    
    print("All auth utils tests passed!")

if __name__ == "__main__":
    test_auth()
