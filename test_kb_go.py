import requests
import time
import sys
import os
import subprocess

def test():
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    
    print("Starting Servers...")
    py_proc = subprocess.Popen([sys.executable, "api/ragflow_server.py"], env=env)
    go_proc = subprocess.Popen(["go", "run", "cmd/ragflow_server.go"], env=env)
    time.sleep(6) # Wait for servers to boot

    try:
        py_url = "http://localhost:9380/api"
        go_url = "http://localhost:9381/api"
        
        # Register via Python (Auth only in Python)
        requests.post(f"{py_url}/register", json={"email": "alice_go@devrag.com", "password": "pass", "tenant_name": "Alice Corp"})
        requests.post(f"{py_url}/register", json={"email": "bob_go@devrag.com", "password": "pass", "tenant_name": "Bob Inc"})

        token_a = requests.post(f"{py_url}/login", json={"email": "alice_go@devrag.com", "password": "pass"}).json()["token"]
        token_b = requests.post(f"{py_url}/login", json={"email": "bob_go@devrag.com", "password": "pass"}).json()["token"]

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        print("--- Create KB via Go ---")
        resp_a = requests.post(f"{go_url}/knowledge-base", json={"name": "Alice Go KB 1"}, headers=headers_a)
        kb_a_id = resp_a.json()["data"]["id"]
        print(f"Alice created KB (Go): {kb_a_id}")

        resp_b = requests.post(f"{go_url}/knowledge-base", json={"name": "Bob Go KB 1"}, headers=headers_b)
        kb_b_id = resp_b.json()["data"]["id"]
        print(f"Bob created KB (Go): {kb_b_id}")

        print("--- List KB Isolation via Go ---")
        list_a = requests.get(f"{go_url}/knowledge-base", headers=headers_a).json()["data"]
        print(f"Alice sees KBs: {[k['name'] for k in list_a]}")
        
        list_b = requests.get(f"{go_url}/knowledge-base", headers=headers_b).json()["data"]
        print(f"Bob sees KBs: {[k['name'] for k in list_b]}")

        print("--- Delete KB Isolation via Go ---")
        del_attempt = requests.delete(f"{go_url}/knowledge-base/{kb_b_id}", headers=headers_a)
        print(f"Alice deleting Bob's KB -> Status: {del_attempt.status_code} (Expected 404)")
        assert del_attempt.status_code == 404

        del_success = requests.delete(f"{go_url}/knowledge-base/{kb_b_id}", headers=headers_b)
        print(f"Bob deleting Bob's KB -> Status: {del_success.status_code} (Expected 200)")
        assert del_success.status_code == 200

        print("\nALL GO KB TESTS PASSED!")

    finally:
        py_proc.terminate()
        go_proc.terminate()
        py_proc.wait()
        go_proc.wait()

if __name__ == "__main__":
    test()
