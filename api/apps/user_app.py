from quart import Blueprint, request, jsonify, g
from quart_auth import login_user, AuthUser, logout_user
from api.db.db_models import User, Tenant, UserTenant, db
from api.utils.auth_utils import hash_password, verify_password
from api.utils.auth_middleware import login_required
import uuid

user_app = Blueprint('user_app', __name__)

@user_app.route('/api/register', methods=['POST'])
async def register():
    data = await request.get_json()
    email = data.get('email')
    password = data.get('password')
    tenant_name = data.get('tenant_name')

    if not email or not password or not tenant_name:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    try:
        if User.select().where(User.email == email).exists():
            return jsonify({"status": "error", "message": "Email already exists"}), 409

        with db.atomic():
            tenant_id = uuid.uuid4().hex
            Tenant.create(id=tenant_id, name=tenant_name, llm_id="default-llm", embd_id="default-embd")

            user_id = uuid.uuid4().hex
            hashed_pw = hash_password(password)
            User.create(id=user_id, email=email, password=hashed_pw, nickname=email.split('@')[0])

            UserTenant.create(id=uuid.uuid4().hex, user_id=user_id, tenant_id=tenant_id, role="owner")

        return jsonify({"status": "ok", "message": "User registered successfully"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@user_app.route('/api/login', methods=['POST'])
async def login():
    data = await request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"status": "error", "message": "Missing credentials"}), 400

    try:
        user = User.get_or_none(User.email == email)
        if not user or not verify_password(password, user.password):
            return jsonify({"status": "error", "message": "Invalid email or password"}), 401

        # Use quart_auth stateful session!
        login_user(AuthUser(user.id))

        return jsonify({"status": "ok", "message": "Login successful"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@user_app.route('/api/logout', methods=['POST'])
@login_required
async def logout():
    logout_user()
    return jsonify({"status": "ok", "message": "Logged out"}), 200

@user_app.route('/api/me', methods=['GET'])
@login_required
async def get_me():
    return jsonify({
        "status": "ok",
        "data": {
            "user_id": g.user_id,
            "tenant_id": g.tenant_id,
            "message": "You are securely authenticated using quart_auth!"
        }
    }), 200
