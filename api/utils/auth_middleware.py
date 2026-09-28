from functools import wraps
from quart import request, jsonify, g
from api.utils.auth_utils import decode_jwt

def login_required(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"status": "error", "message": "Missing or invalid Authorization header"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            payload = decode_jwt(token)
            # Attach user and tenant context to the Quart global g object
            g.user_id = payload.get("user_id")
            g.tenant_id = payload.get("tenant_id")
        except Exception as e:
            return jsonify({"status": "error", "message": f"Token verification failed: {str(e)}"}), 401

        return await f(*args, **kwargs)
    return decorated
