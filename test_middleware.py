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
        
        # Register User A
        requests.post(f"{py_url}/register", json={"email": "alice_auth@devrag.com", "password": "pass", "tenant_name": "Alice Corp"})

        # Login A
        session_a = requests.Session()
        session_a.post(f"{py_url}/login", json={"email": "alice_auth@devrag.com", "password": "pass"})

        print("\n--- Testing Python Middleware ---")
        # 1. No token/session -> 401
        r = requests.get(f"{py_url}/me")
        print(f"No token: {r.status_code} (Expected 401)")
        assert r.status_code == 401

        # 2. Alice session -> 200 (tenant A)
        r = session_a.get(f"{py_url}/me")
        print(f"Alice token: {r.status_code}, data: {r.json()}")
        assert r.status_code == 200
        assert "tenant_id" in r.json()["data"]

        print("\nALL MIDDLEWARE TESTS PASSED WITH QUART_AUTH!")

    finally:
        py_proc.terminate()
        py_proc.wait()

if __name__ == "__main__":
    test()
