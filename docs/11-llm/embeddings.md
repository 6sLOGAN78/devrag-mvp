# Vector Embedding Models

## Level 1: Conceptual Overview

The **Embedding Engine** converts unstructured text chunks and user queries into dense vector representations. It supports batching, automated token truncation, and failover across local (HuggingFace, Ollama, Xinference) and cloud embedding services (OpenAI, DashScope Qwen, Zhipu, BAAI/SiliconFlow, Jina).

```mermaid
graph TD
    Chunker[Document Chunking Pipeline] --> EmbedEngine[Embedding Engine (embedding_model.py)]
    EmbedEngine --> TokenTrunc[Token Truncator (token_utils.py)]
    TokenTrunc --> ProviderDriver{Provider Driver}
    
    ProviderDriver -->|OpenAI SDK| OpenAI[OpenAI / Azure Embed]
    ProviderDriver -->|DashScope Native| DashScope[QWen Embed]
    ProviderDriver -->|Local HTTP| Ollama[Ollama Embed]
    ProviderDriver -->|HuggingFace Hub| Local[Builtin / HuggingFace Embed]
    
    ProviderDriver --> OrderSort[_sorted_by_index Result Re-ordering]
    OrderSort --> DenseVector[Dense Float Vector Output + Token Count]
```

---

## Level 2: Implementation Details

### Source File Map
- **Embedding Subsystem**: [rag/llm/embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L146)
- **Token Utilities**: [common/token_utils.py](file:///home/logan78/Desktop/ragflow/common/token_utils.py)
- **Error Types**: `EmbeddingError` subclassing `ModelException` ([embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L48))

---

### Core Data Structure & Truncation Logic

#### 1. Standard Token Ceiling (`DEFAULT_MAX_TOKENS = 8192`)
In [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L45):
```python
DEFAULT_MAX_TOKENS = 8192
```
To prevent boundary-sized chunks from exceeding provider context limits, text inputs are truncated via `truncate(text, max_tokens)` before calling embedding endpoints.

#### 2. Stable Index Alignment (`_sorted_by_index`)
In [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L58-L62):
```python
def _sorted_by_index(items):
    """Order OpenAI-style SDK embedding items by their `.index` so batched
    results stay aligned with input order even if the provider returns out of order."""
    return sorted(items, key=lambda d: getattr(d, "index", 0))
```

---

### Abstract Base Driver (`Base`)

In [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L146):
```python
class Base(ABC):
    def __init__(self, key, model_name, **kwargs):
        pass

    def get_embedding(self, texts: list[str], max_attempts=5) -> tuple[list[list[float]], int]:
        """Generate dense vector embeddings for input texts.
        Returns (embeddings_list, total_tokens).
        """
        raise NotImplementedError("Please implement get_embedding method!")
```
