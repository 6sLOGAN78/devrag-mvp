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
    
    print("Starting Go API...")
    go_proc = subprocess.Popen(["./ragflow_server"], env=env)
    
    time.sleep(4) # Wait for servers to boot

    try:
        py_url = "http://localhost:9380/api"
        go_url = "http://localhost:9381/api"
        
        # Register User A
        requests.post(f"{py_url}/register", json={"email": "alice@devrag.com", "password": "pass", "tenant_name": "Alice Corp"})
        # Register User B
        requests.post(f"{py_url}/register", json={"email": "bob@devrag.com", "password": "pass", "tenant_name": "Bob Inc"})

        # Login A
        resp_a = requests.post(f"{py_url}/login", json={"email": "alice@devrag.com", "password": "pass"})
        token_a = resp_a.json()["token"]

        # Login B
        resp_b = requests.post(f"{py_url}/login", json={"email": "bob@devrag.com", "password": "pass"})
        token_b = resp_b.json()["token"]

        print(f"Alice Token: {token_a[:15]}...")
        print(f"Bob Token: {token_b[:15]}...")

        print("\n--- Testing Python Middleware ---")
        # 1. No token -> 401
        r = requests.get(f"{py_url}/me")
        print(f"No token: {r.status_code} (Expected 401)")
        assert r.status_code == 401

        # 2. Alice token -> 200 (tenant A)
        r = requests.get(f"{py_url}/me", headers={"Authorization": f"Bearer {token_a}"})
        print(f"Alice token: {r.status_code}, data: {r.json()}")
        assert r.status_code == 200
        assert "tenant_id" in r.json()["data"]

        print("\n--- Testing Go Middleware ---")
        # 1. No token -> 401
        r = requests.get(f"{go_url}/me")
        print(f"No token: {r.status_code} (Expected 401)")
        assert r.status_code == 401

        # 2. Bob token -> 200 (tenant B)
        r = requests.get(f"{go_url}/me", headers={"Authorization": f"Bearer {token_b}"})
        print(f"Bob token: {r.status_code}, data: {r.json()}")
        assert r.status_code == 200
        assert "tenant_id" in r.json()["data"]

        # Assert Alice and Bob have different tenants
        alice_tenant = requests.get(f"{py_url}/me", headers={"Authorization": f"Bearer {token_a}"}).json()["data"]["tenant_id"]
        bob_tenant = requests.get(f"{go_url}/me", headers={"Authorization": f"Bearer {token_b}"}).json()["data"]["tenant_id"]
        print(f"\nAlice Tenant ID: {alice_tenant}")
        print(f"Bob Tenant ID: {bob_tenant}")
        assert alice_tenant != bob_tenant

        print("\nALL MIDDLEWARE TESTS PASSED!")

    finally:
        py_proc.terminate()
        go_proc.terminate()
        py_proc.wait()
        go_proc.wait()

if __name__ == "__main__":
    test()
