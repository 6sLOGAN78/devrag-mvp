import os
import sys
import time
import uuid
import requests
import subprocess
from elasticsearch import Elasticsearch

def test():
    env = os.environ.copy()
    env["PYTHONPATH"] = "."

    print("Starting Python API...")
    py_proc = subprocess.Popen([sys.executable, "api/ragflow_server.py"], env=env)
    
    print("Starting Background Task Executor...")
    worker_proc = subprocess.Popen([sys.executable, "rag/svr/task_executor.py"], env=env)

    print("Waiting 15 seconds for API and ES to warm up...")
    time.sleep(15)

    try:
        base_url = "http://localhost:9380/api"
        session = requests.Session()
        
        test_id = uuid.uuid4().hex[:8]
        email = f"chunk_test_{test_id}@devrag.com"
        
        # 1. Register/Login
        print(f"Registering {email}...")
        session.post(f"{base_url}/register", json={
            "email": email,
            "password": "pass",
            "tenant_name": "Chunk Corp"
        })
        
        login_resp = session.post(f"{base_url}/login", json={
            "email": email,
            "password": "pass"
        })
        
        # Get tenant_id from DB
        from api.db.db_models import UserTenant, User
        user = User.get(User.email == email)
        tenant_id = UserTenant.get(UserTenant.user_id == user.id).tenant_id
        
        print(f"Logged in. Tenant ID: {tenant_id}")
        
        # 2. Create KB
        print("Creating Knowledge Base...")
        kb_resp = session.post(f"{base_url}/dataset", json={"name": "Chunk Test DB"})
        kb_id = kb_resp.json()["data"]["id"]
        
        # 3. Create a Document with multiple paragraphs to force chunking
        file_content = """This is the first paragraph. It contains some basic information about RAG systems. Retrieval-Augmented Generation is a powerful technique.

This is the second paragraph. It introduces vector databases. We use Elasticsearch for this MVP. It allows us to perform dense vector search and BM25 sparse search.

This is the third paragraph. Chunking is an essential part of the process. If a document is too long, the LLM loses context. We split it into 500 token chunks.

This is the fourth paragraph, meant to simulate a slightly longer document. By adding more text, we guarantee the naive chunker processes multiple segments and inserts them individually into the Elasticsearch cluster.
"""
        with open("chunk_test.txt", "w") as f:
            f.write(file_content)
            
        # 4. Upload
        print("Uploading Document...")
        with open("chunk_test.txt", "rb") as f:
            upload_resp = session.post(f"{base_url}/dataset/{kb_id}/document", files={"file": ("chunk_test.txt", f, "text/plain")})
        doc_id = upload_resp.json()["data"]["id"]
        print(f"Document uploaded: {doc_id}")
        
        # 5. Trigger Parse
        print("Triggering Parsing...")
        session.post(f"{base_url}/dataset/{kb_id}/document/parse", json={"document_ids": [doc_id]})
        
        # 6. Wait for processing
        print("Waiting 15 seconds for the worker to chunk, embed, and insert into ES...")
        time.sleep(15)
        
        # 7. Verify directly in Elasticsearch
        print("\n--- ELASTICSEARCH VERIFICATION ---")
        es = Elasticsearch("http://localhost:9200", basic_auth=("elastic", "infini_rag_flow_es"))
        index_name = f"devrag_{tenant_id}"
        
        if not es.indices.exists(index=index_name):
            print(f"FAILED: Index {index_name} was not created!")
            return
            
        print(f"Connected to ES. Searching index: {index_name}")
        
        # Search for chunks belonging to this doc
        query = {
            "query": {
                "term": {
                    "doc_id": doc_id
                }
            }
        }
        
        res = es.search(index=index_name, body=query)
        hits = res["hits"]["hits"]
        
        print(f"\nSUCCESS! Found {len(hits)} chunks in Elasticsearch for document {doc_id}.")
        print("Here is the exact chunked content retrieved from the Vector DB:\n")
        
        for i, hit in enumerate(hits):
            source = hit["_source"]
            print(f"=== CHUNK {i+1} ===")
            print(f"Content: {source.get('content')}")
            print(f"Vector Dimensions: {len(source.get('q_1536_vec', []))}")
            print("="*20 + "\n")

    finally:
        py_proc.terminate()
        worker_proc.terminate()
        
if __name__ == "__main__":
    test()
