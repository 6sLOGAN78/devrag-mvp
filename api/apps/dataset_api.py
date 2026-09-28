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
    parser_id = data.get('parser_id', 'naive') # Support advanced parsing (naive, qa, resume)
    permission = data.get('permission', 'me')

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
            permission=permission,
            parser_id=parser_id
        )
        return jsonify({"status": "ok", "data": {"id": kb.id, "name": kb.name}}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@dataset_app.route('/api/dataset/<kb_id>', methods=['PUT'])
@login_required
async def update_kb(kb_id):
    data = await request.get_json()
    try:
        kb = Knowledgebase.get_or_none(Knowledgebase.id == kb_id, Knowledgebase.tenant_id == g.tenant_id)
        if not kb:
            return jsonify({"status": "error", "message": "Dataset not found or unauthorized"}), 404
            
        if 'parser_id' in data:
            kb.parser_id = data['parser_id']
        if 'parser_config' in data:
            kb.parser_config = data['parser_config']
        if 'name' in data:
            kb.name = data['name']
        if 'description' in data:
            kb.description = data['description']
        
        # Track triggering GraphRAG/RAPTOR tasks
        if 'graphrag_task_id' in data:
            kb.graphrag_task_id = data['graphrag_task_id']
        if 'raptor_task_id' in data:
            kb.raptor_task_id = data['raptor_task_id']
            
        kb.save()
        return jsonify({"status": "ok", "message": "Dataset updated successfully"}), 200
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

@dataset_app.route('/api/dataset/<kb_id>/trigger-graphrag', methods=['POST'])
@login_required
async def trigger_graphrag(kb_id):
    """Simulate dispatching a GraphRAG indexing task to the background worker loop."""
    try:
        kb = Knowledgebase.get_or_none(Knowledgebase.id == kb_id, Knowledgebase.tenant_id == g.tenant_id)
        if not kb:
            return jsonify({"status": "error", "message": "Dataset not found or unauthorized"}), 404
        
        from api.utils.redis_conn import REDIS_CLIENT
        
        # Dispatch task to the stream
        task_id = REDIS_CLIENT.xadd("rag_flow:tasks", {
            "task_type": "graphrag_build",
            "kb_id": kb_id,
            "tenant_id": g.tenant_id
        })
        
        # Track the task in DB
        kb.graphrag_task_id = task_id
        kb.save()
        
        return jsonify({"status": "ok", "message": "GraphRAG task triggered", "task_id": task_id}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
