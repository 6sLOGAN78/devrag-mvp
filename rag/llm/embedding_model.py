import os
import numpy as np

# RAGFlow LLMBundle Abstraction
class LLMBundle:
    def __init__(self, tenant_id=None):
        self.tenant_id = tenant_id
        # In a real app, this would fetch the tenant's model config from DB
        self.api_key = os.environ.get("OPENAI_API_KEY", None)

    def embed(self, texts: list) -> np.ndarray:
        """Embeds a list of strings into 1536-dimensional vectors."""
        if self.api_key:
            import requests
            # Use OpenAI directly (mocking SDK to avoid extra dependencies)
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "input": texts,
                "model": "text-embedding-3-small"
            }
            resp = requests.post("https://api.openai.com/v1/embeddings", headers=headers, json=data)
            if resp.status_code == 200:
                body = resp.json()
                embeddings = [item["embedding"] for item in body["data"]]
                return np.array(embeddings, dtype=np.float32)
            else:
                raise Exception(f"OpenAI API Error: {resp.text}")
        else:
            # Fallback to simulated vectors for MVP offline testing
            # Generates a normalized 1536-dim vector deterministically based on text length
            vectors = []
            for t in texts:
                np.random.seed(len(t))
                vec = np.random.rand(1536).astype(np.float32)
                vec = vec / np.linalg.norm(vec)
                vectors.append(vec.tolist())
            return np.array(vectors)

def embed_chunks(chunks: list, tenant_id: str):
    """Takes chunk dicts, embeds content, adds vector to dict."""
    llm = LLMBundle(tenant_id)
    
    # Extract strings
    texts = [c["content"] for c in chunks]
    
    # Embed
    vectors = llm.embed(texts)
    
    # Append to chunks
    for i, chunk in enumerate(chunks):
        chunk["q_1536_vec"] = vectors[i].tolist()
        
    return chunks
