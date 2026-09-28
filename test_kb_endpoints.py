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
        requests.post(f"{py_url}/register", json={"email": "alice_kb@devrag.com", "password": "pass", "tenant_name": "Alice Corp"})
        requests.post(f"{py_url}/register", json={"email": "bob_kb@devrag.com", "password": "pass", "tenant_name": "Bob Inc"})

        # Login A & B
        token_a = requests.post(f"{py_url}/login", json={"email": "alice_kb@devrag.com", "password": "pass"}).json()["token"]
        token_b = requests.post(f"{py_url}/login", json={"email": "bob_kb@devrag.com", "password": "pass"}).json()["token"]

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        print("--- Create KB ---")
        resp_a = requests.post(f"{py_url}/knowledge-base", json={"name": "Alice KB 1"}, headers=headers_a)
        kb_a_id = resp_a.json()["data"]["id"]
        print(f"Alice created KB: {kb_a_id}")

        resp_b = requests.post(f"{py_url}/knowledge-base", json={"name": "Bob KB 1"}, headers=headers_b)
        kb_b_id = resp_b.json()["data"]["id"]
        print(f"Bob created KB: {kb_b_id}")

        print("--- List KB Isolation ---")
        list_a = requests.get(f"{py_url}/knowledge-base", headers=headers_a).json()["data"]
        print(f"Alice sees KBs: {[k['name'] for k in list_a]}")
        assert len(list_a) == 1 and list_a[0]["id"] == kb_a_id
        
        list_b = requests.get(f"{py_url}/knowledge-base", headers=headers_b).json()["data"]
        print(f"Bob sees KBs: {[k['name'] for k in list_b]}")
        assert len(list_b) == 1 and list_b[0]["id"] == kb_b_id

        print("--- Delete KB Isolation ---")
        # Alice tries to delete Bob's KB
        del_attempt = requests.delete(f"{py_url}/knowledge-base/{kb_b_id}", headers=headers_a)
        print(f"Alice deleting Bob's KB -> Status: {del_attempt.status_code} (Expected 404)")
        assert del_attempt.status_code == 404

        # Bob successfully deletes his own KB
        del_success = requests.delete(f"{py_url}/knowledge-base/{kb_b_id}", headers=headers_b)
        print(f"Bob deleting Bob's KB -> Status: {del_success.status_code} (Expected 200)")
        assert del_success.status_code == 200

        print("\nALL KB TESTS PASSED!")

    finally:
        py_proc.terminate()
        py_proc.wait()

if __name__ == "__main__":
    test()
