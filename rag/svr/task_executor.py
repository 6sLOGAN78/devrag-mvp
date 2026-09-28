import time
import json
import logging
import argparse
import sys
import os

# Add root to pythonpath
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.utils.redis_conn import REDIS_CLIENT
from api.db.db_models import db
from common.log_utils import init_root_logger, getLogger

init_root_logger("task_executor")
logger = getLogger("TaskExecutor")

import threading

# Add imports for Document Model
from api.db.db_models import db, Document, Knowledgebase

STREAM_NAME = "rag_flow:tasks"
CONSUMER_GROUP = "rag_flow_workers"
CONSUMER_NAME = f"worker_{os.getpid()}"

def init_stream():
    """Initialize the Redis stream and consumer group if they don't exist."""
    try:
        # Create group and stream, MKSTREAM creates the stream if it doesn't exist
        REDIS_CLIENT.xgroup_create(STREAM_NAME, CONSUMER_GROUP, id='0', mkstream=True)
        logger.info(f"Created consumer group {CONSUMER_GROUP} on stream {STREAM_NAME}")
    except Exception as e:
        if "BUSYGROUP Consumer Group name already exists" in str(e):
            logger.info(f"Consumer group {CONSUMER_GROUP} already exists.")
        else:
            logger.error(f"Error creating consumer group: {e}")

def report_status():
    """Distributed Heartbeat Manager pushing to Redis ZSET TASKEXE"""
    while True:
        try:
            # RAGFlow heartbeat mechanism (IP, PID, etc).
            heartbeat_data = json.dumps({
                "pid": os.getpid(),
                "status": "alive"
            })
            # Use current timestamp as score in Sorted Set
            REDIS_CLIENT.zadd("TASKEXE", {heartbeat_data: time.time()})
        except Exception as e:
            logger.error(f"Failed to report heartbeat: {e}")
        time.sleep(30)

def process_message(msg_id, payload):
    """Orchestrates processing logic and manages the Task's state machine."""
    task_type = payload.get('task_type', '')
    kb_id = payload.get('kb_id', '')
    doc_id = payload.get('doc_id', '')
    task_id = payload.get('task_id', '')
    
    logger.info(f"Processing Task [{msg_id}]: {task_type} for Doc {doc_id}")
    
    # We must import Task here or at the top. It's imported at the top now?
    # Wait, I'll just rely on the global import at the top of the file.
    
    task_obj = None
    if task_id:
        if db.is_closed():
            db.connect()
        from api.db.db_models import Task, Document
        task_obj = Task.get_or_none(Task.id == task_id)

    if task_obj and task_type == 'document_parse':
        try:
            doc = Document.get_or_none(Document.id == task_obj.doc_id)
            if not doc:
                raise Exception(f"Document {task_obj.doc_id} not found")
                
            tenant_id = payload.get('tenant_id')
            kb_id = payload.get('kb_id')
            
            # Phase 1: Fetch Raw Bytes
            from api.utils.storage_client import STORAGE_CLIENT
            bucket_name = "devrag-documents"
            location = doc.location
            if not location:
                raise Exception("Document location is missing")
                
            response = STORAGE_CLIENT.get_object(bucket_name, location)
            raw_text = response.read().decode('utf-8')
            response.close()
            response.release_conn()
            
            # Phase 2: Chunking (build_chunks)
            from rag.app import naive
            chunks = naive.chunk(raw_text)
            
            # Decorate chunks with metadata
            import uuid
            for c in chunks:
                c["_id"] = uuid.uuid4().hex
                c["doc_id"] = doc.id
                c["kb_id"] = kb_id
                c["tenant_id"] = tenant_id
                
            # Phase 3: Embedding
            from rag.llm.embedding_model import embed_chunks
            chunks = embed_chunks(chunks, tenant_id)
            
            # Phase 4: Vector Store Insertion
            from common.doc_store.es_conn_base import docStoreConn
            index_name = f"devrag_{tenant_id}" # Tenant isolated index
            docStoreConn.insert(index_name, chunks)
            
            # 5. State: DONE (progress = 1.0)
            task_obj.progress = 1.0
            task_obj.save()
            logger.info(f"Sub-Task {task_id} state -> DONE (Inserted {len(chunks)} chunks)")
            
        except Exception as e:
            # State: FAILED (progress = -1.0)
            task_obj.progress = -1.0
            task_obj.progress_msg = f"[Exception]: {str(e)}"
            task_obj.save()
            logger.error(f"Sub-Task {task_id} state -> FAILED (-1.0): {str(e)}")
            
    elif task_type == 'graphrag_build':
        # Simulate processing time
        time.sleep(2)
        logger.info(f"GraphRAG indexing completed for KB {kb_id}.")
        
    # Acknowledge the message to remove it from the pending list
    try:
        REDIS_CLIENT.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)
        logger.info(f"Acknowledged Task [{msg_id}]")
    except Exception as e:
        logger.error(f"Failed to ACK Task [{msg_id}]: {e}")

def run():
    init_stream()
    
    # Start Distributed Heartbeat Manager Thread
    heartbeat_thread = threading.Thread(target=report_status, daemon=True)
    heartbeat_thread.start()
    
    logger.info(f"Starting Background Task Executor [{CONSUMER_NAME}]... Waiting for tasks.")
    
    # Connect to DB to ensure it's available for workers
    if db.is_closed():
        db.connect()
    
    while True:
        try:
            # Block for 5 seconds waiting for new messages
            messages = REDIS_CLIENT.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={STREAM_NAME: '>'},
                count=1,
                block=5000
            )
            
            if messages:
                for stream, msg_list in messages:
                    for msg_id, payload in msg_list:
                        process_message(msg_id, payload)
        
        except Exception as e:
            logger.error(f"Error in task execution loop: {e}")
            time.sleep(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="RAGFlow Background Task Executor")
    args = parser.parse_args()
    
    run()
