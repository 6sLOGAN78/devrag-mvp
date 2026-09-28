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
    """Orchestrates processing logic and manages the Document's state machine."""
    task_type = payload.get('task_type', '')
    kb_id = payload.get('kb_id', '')
    doc_id = payload.get('doc_id', '')
    
    logger.info(f"Processing Task [{msg_id}]: {task_type} for KB {kb_id}")
    
    doc = None
    if doc_id:
        # Avoid peewee connection issues across threads by ensuring connection
        if db.is_closed():
            db.connect()
        doc = Document.get_or_none(Document.id == doc_id)

    if doc and task_type == 'document_parse':
        try:
            # 1. State: RUNNING ('2')
            doc.status = '2'
            doc.save()
            logger.info(f"Document {doc_id} state -> RUNNING")

            # Simulate processing time / parsing logic (OCR, NLP chunking)
            time.sleep(2)
            
            # 2. State: DONE ('3')
            doc.status = '3'
            doc.progress = 1.0
            doc.save()
            logger.info(f"Document {doc_id} state -> DONE")
            
        except Exception as e:
            # 3. State: FAILED ('4')
            if doc:
                doc.status = '4'
                doc.progress_msg = f"[Exception]: {str(e)}"
                doc.save()
            logger.error(f"Document {doc_id} state -> FAILED: {str(e)}")
            
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
