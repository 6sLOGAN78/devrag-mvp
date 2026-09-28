import requests
import time
import sys
import os
import subprocess
from api.db.db_models import Document, db

def test():
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    
    print("Starting Python API...")
    py_proc = subprocess.Popen([sys.executable, "api/ragflow_server.py"], env=env)
    
    print("Starting Background Task Executor...")
    worker_proc = subprocess.Popen([sys.executable, "rag/svr/task_executor.py"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    time.sleep(3) # Wait for servers to boot

    try:
        base_url = "http://localhost:9380/api"
        session = requests.Session()
        
        # 1. Register/Login
        session.post(f"{base_url}/register", json={
            "email": "test_state@devrag.com",
            "password": "pass",
            "tenant_name": "State Corp"
        })
        session.post(f"{base_url}/login", json={
            "email": "test_state@devrag.com",
            "password": "pass"
        })

        # 2. Create Dataset
        resp = session.post(f"{base_url}/dataset", json={"name": "State Dataset 1"})
        kb_id = resp.json()["data"]["id"]
        
        # 3. Upload Document
        with open("state_test.txt", "w") as f:
            f.write("Test content")
        with open("state_test.txt", "rb") as f:
            upload_resp = session.post(
                f"{base_url}/dataset/{kb_id}/document",
                files={"file": ("state_test.txt", f, "text/plain")}
            )
        doc_id = upload_resp.json()["data"]["id"]
        
        db.connect()
        doc = Document.get_by_id(doc_id)
        print(f"Initial Document Run State: '{doc.run}' (Expected '0' / UNSTART)")
        assert doc.run == '0'
        
        # 4. Trigger Parsing
        print("Triggering Parsing...")
        session.post(f"{base_url}/dataset/{kb_id}/document/parse", json={"document_ids": [doc_id]})
        
        # 5. Wait for worker and verify state
        # The aggregation thread takes 6 seconds, we'll wait 8 seconds.
        print("Waiting 15 seconds for worker and aggregation thread to process...")
        time.sleep(15)
        
        doc = Document.get_by_id(doc_id)
        print(f"Final Document Run State: '{doc.run}' (Expected '3' / DONE)")
        assert doc.run == '3'
        assert doc.progress == 1.0
        
        print("\nALL WORKER STATE TESTS PASSED!")

    finally:
        py_proc.terminate()
        py_proc.wait()
        worker_proc.terminate()
        worker_proc.wait()
        if os.path.exists("state_test.txt"):
            os.remove("state_test.txt")
        db.close()

if __name__ == "__main__":
    test()
