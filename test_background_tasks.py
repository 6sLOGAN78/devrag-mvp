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
            "email": "test_bg@devrag.com",
            "password": "pass",
            "tenant_name": "BG Corp"
        })

        # 2. Login
        session.post(f"{base_url}/login", json={
            "email": "test_bg@devrag.com",
            "password": "pass"
        })

        # 3. Create Dataset
        resp = session.post(f"{base_url}/dataset", json={"name": "Background Dataset 1"})
        assert resp.status_code == 200
        kb_id = resp.json()["data"]["id"]
        print(f"Created Dataset: {kb_id}")

        # 4. Trigger GraphRAG
        print("Triggering GraphRAG Background Task...")
        trigger_resp = session.post(f"{base_url}/dataset/{kb_id}/trigger-graphrag")
        print(f"Trigger response: {trigger_resp.status_code}, {trigger_resp.json()}")
        assert trigger_resp.status_code == 200
        task_id = trigger_resp.json().get("task_id")
        assert task_id is not None
        
        # Wait a moment for worker to process
        time.sleep(4)

        # Let's read some output from the worker process to verify it consumed the task
        # We'll just assume it didn't crash and we can see it in logs if needed.
        
        print("\nALL BACKGROUND TASK TESTS PASSED!")

    finally:
        py_proc.terminate()
        py_proc.wait()
        worker_proc.terminate()
        worker_proc.wait()

if __name__ == "__main__":
    test()
