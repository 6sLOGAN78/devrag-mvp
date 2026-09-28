from quart import Blueprint, request, jsonify, g
from api.db.db_models import Knowledgebase, db
from api.utils.auth_middleware import login_required
import uuid

dataset_app = Blueprint('dataset_app', __name__)

@dataset_app.route('/api/dataset', methods=['POST'])
@login_required
async def create_kb():
    data = await request.get_json()
    name = data.get('name')
    description = data.get('description', '')

    if not name:
        return jsonify({"status": "error", "message": "Missing name"}), 400

    try:
        kb_id = uuid.uuid4().hex
        kb = Knowledgebase.create(
            id=kb_id,
            tenant_id=g.tenant_id,
            name=name,
            description=description,
            created_by=g.user_id,
            embd_id="default-embd",
            permission="me",
            parser_id="naive"
        )
        return jsonify({"status": "ok", "data": {"id": kb.id, "name": kb.name}}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@dataset_app.route('/api/dataset', methods=['GET'])
@login_required
async def list_kbs():
    try:
        # STRICT TENANT ISOLATION
        query = Knowledgebase.select().where(Knowledgebase.tenant_id == g.tenant_id)
        kbs = []
        for row in query:
            kbs.append({
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "created_by": row.created_by,
                "created_at": row.create_time
            })
        return jsonify({"status": "ok", "data": kbs}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@dataset_app.route('/api/dataset/<kb_id>', methods=['DELETE'])
@login_required
async def delete_kb(kb_id):
    try:
        # STRICT TENANT ISOLATION
        query = Knowledgebase.delete().where(
            (Knowledgebase.id == kb_id) & 
            (Knowledgebase.tenant_id == g.tenant_id)
        )
        deleted = query.execute()
        if deleted == 0:
            return jsonify({"status": "error", "message": "KB not found or unauthorized"}), 404
            
        return jsonify({"status": "ok", "message": "KB deleted successfully"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
