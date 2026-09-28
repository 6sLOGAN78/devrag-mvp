from quart import Blueprint, request, jsonify, g
from api.db.db_models import Knowledgebase, Document, Task, db
from api.utils.auth_middleware import login_required
from api.utils.storage_client import STORAGE_CLIENT
from api.utils.redis_conn import REDIS_CLIENT
from io import BytesIO
import xxhash
import uuid

document_app = Blueprint('document_app', __name__)

@document_app.route('/api/dataset/<dataset_id>/document', methods=['POST'])
@login_required
async def upload_document(dataset_id):
    # Security: Verify KB ownership
    kb = Knowledgebase.get_or_none(Knowledgebase.id == dataset_id, Knowledgebase.tenant_id == g.tenant_id)
    if not kb:
        return jsonify({"status": "error", "message": "no authorization"}), 403

    files = await request.files
    if 'file' not in files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400

    file = files['file']
    filename = file.filename
    blob = file.read()
    
    # 1. Deduplication and Hashing
    new_hash = xxhash.xxh128(blob).hexdigest()
    
    # Check if duplicate in this KB
    existing = Document.get_or_none(Document.kb_id == kb.id, Document.content_hash == new_hash)
    if existing:
        return jsonify({"status": "error", "message": "File already exists in this Knowledge Base", "data": {"id": existing.id}}), 409

    # 2. MinIO / S3 Storage Abstraction
    # Ensure bucket exists
    bucket_name = "devrag-documents"
    if not STORAGE_CLIENT.bucket_exists(bucket_name):
        STORAGE_CLIENT.make_bucket(bucket_name)

    doc_id = uuid.uuid4().hex
    location = f"{g.tenant_id}/{kb.id}/{doc_id}-{filename}"
    
    STORAGE_CLIENT.put_object(
        bucket_name,
        location,
        BytesIO(blob),
        length=len(blob)
    )

    # 3. Database Registration (Initial Status: UNSTART -> '1')
    try:
        doc = Document.create(
            id=doc_id,
            kb_id=kb.id,
            parser_id=kb.parser_id,
            created_by=g.user_id,
            type=filename.split('.')[-1] if '.' in filename else "unknown",
            name=filename,
            location=location,
            size=len(blob),
            content_hash=new_hash,
            status='1' # UNSTART
        )
        return jsonify({"status": "ok", "message": "Document uploaded successfully", "data": {"id": doc.id}}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@document_app.route('/api/dataset/<dataset_id>/document/parse', methods=['POST'])
@login_required
async def parse_documents(dataset_id):
    # Security: Verify KB ownership
    kb = Knowledgebase.get_or_none(Knowledgebase.id == dataset_id, Knowledgebase.tenant_id == g.tenant_id)
    if not kb:
        return jsonify({"status": "error", "message": "no authorization"}), 403

    data = await request.get_json()
    doc_ids = data.get('document_ids', [])
    
    if not doc_ids:
        return jsonify({"status": "error", "message": "No document IDs provided"}), 400

    dispatched = []
    
    for doc_id in doc_ids:
        doc = Document.get_or_none(Document.id == doc_id, Document.kb_id == kb.id)
        if not doc:
            continue
            
        # Update run state to RUNNING ('1' for execution logic)
        doc.run = '1'
        doc.save()
        
        # 1. Create sub-task records in DB (Task Chunking Simulation)
        task_id = uuid.uuid4().hex
        task = Task.create(
            id=task_id,
            doc_id=doc.id,
            from_page=0,
            to_page=1000000,
            task_type="document_parse"
        )
        
        # 2. Redis Queueing (Push sub-tasks to Stream)
        task_payload = {
            "task_type": "document_parse",
            "task_id": task.id,
            "doc_id": doc.id,
            "kb_id": kb.id,
            "tenant_id": g.tenant_id
        }
        
        REDIS_CLIENT.xadd("rag_flow:tasks", task_payload)
        dispatched.append({"doc_id": doc.id, "task_id": task.id})

    return jsonify({"status": "ok", "message": "Parsing tasks queued", "data": dispatched}), 200

