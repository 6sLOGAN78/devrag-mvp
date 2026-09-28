# OpenAI & Azure OpenAI Integration

## Level 1: Conceptual Overview

OpenAI and Azure OpenAI serve as primary model providers in RAGFlow for Chat (`gpt-4o`, `gpt-4-turbo`, `o1`, `o3-mini`), Embeddings (`text-embedding-3-small`, `text-embedding-3-large`), and Vision/Audio processing. Integration is implemented via both direct OpenAI SDK calls and LiteLLM wrappers.

---

## Level 2: Implementation Details

### Source File References
- **Chat Driver**: [chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L1062) (`OpenAI_APIChat`, `LiteLLMBase`)
- **Embedding Driver**: [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L258) (`OpenAIEmbed`, `AzureEmbed`)
- **Rerank Adapter**: [rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L255) (`OpenAI_APIRerank`)

---

### Implementation Details

#### 1. OpenAI Embeddings (`OpenAIEmbed`)
In [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L258-L280):

```python
class OpenAIEmbed(Base):
    def __init__(self, key, model_name="text-embedding-3-small", base_url="https://api.openai.com/v1", **kwargs):
        self.client = OpenAI(api_key=key, base_url=ensure_v1(base_url))
        self.model_name = model_name

    def get_embedding(self, texts, max_attempts=5):
        # Truncates batch items to DEFAULT_MAX_TOKENS (8192)
        # Orders returned embeddings using _sorted_by_index
        resp = self.client.embeddings.create(input=texts, model=self.model_name)
        embeddings = [d.embedding for d in _sorted_by_index(resp.data)]
        return embeddings, resp.usage.total_tokens
```

#### 2. Azure OpenAI Deployment Mapping (`AzureEmbed`)
In [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L319-L330):
Azure OpenAI overrides `base_url` resolution to target deployment endpoints (`https://{resource}.openai.azure.com/openai/deployments/{deployment}/embeddings?api-version=...`).

---

### Parameter Handling for O1 / O3 Reasoning Models

For reasoning-focused models (`o1-preview`, `o1-mini`, `o3-mini`), traditional `temperature` parameters are suppressed, and `max_completion_tokens` replaces `max_tokens` ([chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L73-L96)).
