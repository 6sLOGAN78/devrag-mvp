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
    time.sleep(3) # Wait for servers to boot

    try:
        py_url = "http://localhost:9380/api"
        
        # Register User A (Alice) & User B (Bob)
        requests.post(f"{py_url}/register", json={"email": "alice_dataset@devrag.com", "password": "pass", "tenant_name": "Alice Corp"})
        requests.post(f"{py_url}/register", json={"email": "bob_dataset@devrag.com", "password": "pass", "tenant_name": "Bob Inc"})

        session_a = requests.Session()
        session_b = requests.Session()

        # Login A & B
        session_a.post(f"{py_url}/login", json={"email": "alice_dataset@devrag.com", "password": "pass"})
        session_b.post(f"{py_url}/login", json={"email": "bob_dataset@devrag.com", "password": "pass"})

        print("--- Create Dataset ---")
        resp_a = session_a.post(f"{py_url}/dataset", json={"name": "Alice Dataset 1"})
        kb_a_id = resp_a.json()["data"]["id"]
        print(f"Alice created Dataset: {kb_a_id}")

        resp_b = session_b.post(f"{py_url}/dataset", json={"name": "Bob Dataset 1"})
        kb_b_id = resp_b.json()["data"]["id"]
        print(f"Bob created Dataset: {kb_b_id}")

        print("--- List Dataset Isolation ---")
        list_a = session_a.get(f"{py_url}/dataset").json()["data"]
        print(f"Alice sees Datasets: {[k['name'] for k in list_a]}")
        assert len(list_a) == 1 and list_a[0]["id"] == kb_a_id
        
        list_b = session_b.get(f"{py_url}/dataset").json()["data"]
        print(f"Bob sees Datasets: {[k['name'] for k in list_b]}")
        assert len(list_b) == 1 and list_b[0]["id"] == kb_b_id

        print("--- Delete Dataset Isolation ---")
        # Alice tries to delete Bob's Dataset
        del_attempt = session_a.delete(f"{py_url}/dataset/{kb_b_id}")
        print(f"Alice deleting Bob's Dataset -> Status: {del_attempt.status_code} (Expected 404)")
        assert del_attempt.status_code == 404

        # Bob successfully deletes his own Dataset
        del_success = session_b.delete(f"{py_url}/dataset/{kb_b_id}")
        print(f"Bob deleting Bob's Dataset -> Status: {del_success.status_code} (Expected 200)")
        assert del_success.status_code == 200

        print("\nALL DATASET TESTS PASSED WITH QUART_AUTH!")

    finally:
        py_proc.terminate()
        py_proc.wait()

if __name__ == "__main__":
    test()
