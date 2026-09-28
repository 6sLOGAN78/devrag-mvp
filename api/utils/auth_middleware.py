from functools import wraps
from quart import request, jsonify, g
from quart_auth import current_user, Unauthorized
from api.db.db_models import User, UserTenant

def login_required(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        if not await current_user.is_authenticated:
            return jsonify({"status": "error", "message": "Authorization is not valid!"}), 401
        
        # Load user from db
        user_id = current_user.auth_id
        user = User.get_or_none(User.id == user_id)
        if not user:
            return jsonify({"status": "error", "message": "User not found"}), 401
            
        g.user = user
        g.user_id = user_id
        
        # Determine tenant_id from UserTenant mapping just like original RAGFlow does indirectly
        user_tenant = UserTenant.get_or_none(UserTenant.user_id == user_id)
        if user_tenant:
            g.tenant_id = user_tenant.tenant_id
        else:
            g.tenant_id = None
            
        return await f(*args, **kwargs)
    return decorated
