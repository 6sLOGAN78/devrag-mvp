from quart import Blueprint, request, jsonify, g
from api.utils.auth_middleware import login_required
from api.db.db_models import TenantLLM
import uuid

llm_app = Blueprint('llm_app', __name__)

@llm_app.route('/api/llm/keys', methods=['GET'])
@login_required
async def get_keys():
    keys = TenantLLM.select().where(TenantLLM.tenant_id == g.tenant_id)
    key_list = []
    for k in keys:
        # Mask the key for security, only showing last 4 characters
        masked = f"***...{k.api_key[-4:]}" if len(k.api_key) >= 4 else "***"
        key_list.append({
            "provider": k.provider,
            "masked_key": masked
        })
    return jsonify({"status": "ok", "data": key_list})

@llm_app.route('/api/llm/keys', methods=['POST'])
@login_required
async def set_key():
    req_data = await request.get_json()
    provider = req_data.get('provider')
    api_key = req_data.get('api_key')
    
    if not provider or not api_key:
        return jsonify({"status": "error", "message": "Provider and API Key are required"}), 400
        
    if provider not in ['openai', 'openrouter']:
        return jsonify({"status": "error", "message": "Invalid provider. Must be openai or openrouter"}), 400
        
    # Check if a key already exists for this provider
    existing_key = TenantLLM.get_or_none((TenantLLM.tenant_id == g.tenant_id) & (TenantLLM.provider == provider))
    
    if existing_key:
        existing_key.api_key = api_key
        existing_key.save()
    else:
        TenantLLM.create(
            id=uuid.uuid4().hex,
            tenant_id=g.tenant_id,
            provider=provider,
            api_key=api_key
        )
        
    return jsonify({"status": "ok", "message": f"{provider} API key saved successfully"})
