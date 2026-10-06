# Ollama Local Model Integration

## Level 1: Conceptual Overview

**Ollama** enables zero-cost local LLM inference in RAGFlow for offline deployments, privacy-sensitive environments, and edge hardware. It supports chat completion (`llama3`, `qwen2.5`, `mistral`, `deepseek-r1`) and local embedding models (`nomic-embed-text`, `bge-m3`).

---

## Level 2: Implementation Details

### Source File References
- **Chat Driver**: [chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L1635) (`LiteLLMBase` mapped via `ollama/...`)
- **Embedding Driver**: [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L478) (`OllamaEmbed`)

---

### Implementation Details

#### 1. Ollama Embedding Driver (`OllamaEmbed`)
In [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L478-L520):

```python
class OllamaEmbed(Base):
    def __init__(self, key, model_name, base_url="http://127.0.0.1:11434", **kwargs):
        self.client = Client(host=base_url)
        self.model_name = model_name

    def get_embedding(self, texts, max_attempts=5):
        # Uses python ollama SDK client.embeddings or client.embed
        res = self.client.embed(model=self.model_name, input=texts)
        embeddings = res["embeddings"]
        # Calculates approximate token usage
        token_count = sum(num_tokens_from_string(t) for t in texts)
        return embeddings, token_count
```

#### 2. Base URL Handling & Host Formatting
Ollama instances require base URLs formatted without `/v1` path suffixes (e.g. `http://localhost:11434` or `http://host.docker.internal:11434`). The `FACTORY_DEFAULT_BASE_URL` ([rag/llm/__init__.py](file:///home/logan78/Desktop/ragflow/rag/llm/__init__.py#L73)) leaves Ollama base URL empty by default so users can configure local endpoints.
