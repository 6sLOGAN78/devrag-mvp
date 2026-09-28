from quart import Blueprint, request, jsonify
from api.db.db_models import User, Tenant, UserTenant, db
from api.utils.auth_utils import hash_password, verify_password, generate_jwt
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
        # Check if user already exists
        if User.select().where(User.email == email).exists():
            return jsonify({"status": "error", "message": "Email already exists"}), 409

        # Transaction for atomic creation
        with db.atomic():
            # 1. Create Tenant
            tenant_id = uuid.uuid4().hex
            Tenant.create(
                id=tenant_id,
                name=tenant_name,
                llm_id="default-llm",
                embd_id="default-embd"
            )

            # 2. Create User
            user_id = uuid.uuid4().hex
            hashed_pw = hash_password(password)
            User.create(
                id=user_id,
                email=email,
                password=hashed_pw,
                nickname=email.split('@')[0]
            )

            # 3. Create UserTenant relationship (Owner)
            UserTenant.create(
                id=uuid.uuid4().hex,
                user_id=user_id,
                tenant_id=tenant_id,
                role="owner"
            )

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
        # Find User
        user = User.get_or_none(User.email == email)
        if not user:
            return jsonify({"status": "error", "message": "Invalid email or password"}), 401

        # Verify Password
        if not verify_password(password, user.password):
            return jsonify({"status": "error", "message": "Invalid email or password"}), 401

        # Find Tenant
        user_tenant = UserTenant.get_or_none(UserTenant.user_id == user.id)
        tenant_id = user_tenant.tenant_id if user_tenant else ""

        # Generate JWT
        token = generate_jwt(user.id, tenant_id)

        return jsonify({"status": "ok", "token": token}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

from api.utils.auth_middleware import login_required
from quart import g

@user_app.route('/api/me', methods=['GET'])
@login_required
async def get_me():
    # Option B: strict tenancy scoping extraction
    tenant_id = g.tenant_id
    user_id = g.user_id

    # For MVP, just return the data securely
    return jsonify({
        "status": "ok",
        "data": {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "message": "You are securely authenticated and scoped to your tenant."
        }
    }), 200
