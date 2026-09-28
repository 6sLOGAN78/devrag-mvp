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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TaskExecutor")

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

def process_message(msg_id, payload):
    """Simulate document parsing or advanced indexing execution."""
    task_type = payload.get('task_type', '')
    kb_id = payload.get('kb_id', '')
    
    logger.info(f"Processing Task [{msg_id}]: {task_type} for KB {kb_id}")
    
    # Simulate processing time
    time.sleep(2)
    
    if task_type == 'graphrag_build':
        logger.info(f"GraphRAG indexing completed for KB {kb_id}.")
    elif task_type == 'document_parse':
        logger.info(f"Document parsing completed for KB {kb_id}.")
        
    # Acknowledge the message to remove it from the pending list
    REDIS_CLIENT.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)
    logger.info(f"Acknowledged Task [{msg_id}]")

def run():
    init_stream()
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
