import requests
import time
import sys
import os
import subprocess

def test():
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    proc = subprocess.Popen([sys.executable, "api/ragflow_server.py"], env=env)
    time.sleep(3) # Wait for server to boot

    try:
        base_url = "http://localhost:9380/api"
        
        session = requests.Session()

        # 1. Register
        print("Testing Registration...")
        reg_resp = session.post(f"{base_url}/register", json={
            "email": "test_auth@devrag.com",
            "password": "SecurePassword123!",
            "tenant_name": "DevRAG Workspace"
        })
        print(f"Register status: {reg_resp.status_code}, response: {reg_resp.text}")
        assert reg_resp.status_code in [200, 409] 

        # 2. Login
        print("Testing Login...")
        login_resp = session.post(f"{base_url}/login", json={
            "email": "test_auth@devrag.com",
            "password": "SecurePassword123!"
        })
        print(f"Login status: {login_resp.status_code}, response: {login_resp.text}")
        assert login_resp.status_code == 200
        
        # Verify cookie is set
        cookies = session.cookies.get_dict()
        assert "ragflow_session" in cookies
        print(f"Acquired Auth Cookie: {cookies['ragflow_session'][:20]}...")

        print("\nALL AUTH ENDPOINT TESTS PASSED WITH QUART_AUTH!")
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    test()
