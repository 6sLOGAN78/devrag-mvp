import requests
import time
import sys
import os
import subprocess

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
        
        # 1. Register
        session.post(f"{base_url}/register", json={
            "email": "test_upload@devrag.com",
            "password": "pass",
            "tenant_name": "Upload Corp"
        })

        # 2. Login
        session.post(f"{base_url}/login", json={
            "email": "test_upload@devrag.com",
            "password": "pass"
        })

        # 3. Create Dataset
        resp = session.post(f"{base_url}/dataset", json={"name": "Upload Dataset 1"})
        assert resp.status_code == 200
        kb_id = resp.json()["data"]["id"]
        print(f"Created Dataset: {kb_id}")

        # 4. Upload Document
        print("Uploading Document...")
        # Create a dummy file
        with open("dummy_test.txt", "w") as f:
            f.write("This is a test document for devRag.")
            
        with open("dummy_test.txt", "rb") as f:
            upload_resp = session.post(
                f"{base_url}/dataset/{kb_id}/document",
                files={"file": ("dummy_test.txt", f, "text/plain")}
            )
            
        print(f"Upload response: {upload_resp.status_code}, {upload_resp.json()}")
        assert upload_resp.status_code == 200
        doc_id = upload_resp.json()["data"]["id"]
        
        # 5. Trigger Parsing
        print("Triggering Parsing...")
        parse_resp = session.post(f"{base_url}/dataset/{kb_id}/document/parse", json={"document_ids": [doc_id]})
        print(f"Parse response: {parse_resp.status_code}, {parse_resp.json()}")
        assert parse_resp.status_code == 200
        
        # Wait a moment for worker to process
        time.sleep(4)
        
        print("\nALL UPLOAD AND PARSE TESTS PASSED!")

    finally:
        py_proc.terminate()
        py_proc.wait()
        worker_proc.terminate()
        worker_proc.wait()
        if os.path.exists("dummy_test.txt"):
            os.remove("dummy_test.txt")

if __name__ == "__main__":
    test()
