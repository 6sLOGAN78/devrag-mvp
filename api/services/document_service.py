import threading
import time
from api.db.db_models import Document, Task, db
from api.utils.redis_conn import REDIS_CLIENT
from common.log_utils import getLogger

logger = getLogger("DocumentService")

def update_progress():
    """Background Aggregation Thread to update Document state from Tasks."""
    while True:
        try:
            if db.is_closed():
                db.connect()
                
            # Find all documents that are currently processing (run='1')
            running_docs = Document.select().where(Document.run == '1')
            
            for doc in running_docs:
                tasks = list(Task.select().where(Task.doc_id == doc.id))
                if not tasks:
                    continue
                    
                total_progress = 0.0
                has_failure = False
                
                for task in tasks:
                    if task.progress < 0:
                        has_failure = True
                        doc.progress_msg = task.progress_msg
                        break
                    total_progress += task.progress
                    
                avg_progress = total_progress / len(tasks)
                doc.progress = avg_progress
                
                if has_failure:
                    doc.run = '4' # FAIL
                    doc.save()
                    logger.warning(f"Document {doc.id} marked as FAILED")
                elif avg_progress >= 1.0:
                    doc.run = '3' # DONE
                    doc.save()
                    logger.info(f"Document {doc.id} marked as DONE")
                else:
                    doc.save()
                    
        except Exception as e:
            logger.error(f"Error in update_progress aggregation: {e}")
            
        time.sleep(6) # Loop every 6 seconds exactly like RAGFlow

def start_aggregation_thread():
    t = threading.Thread(target=update_progress, daemon=True)
    t.start()
