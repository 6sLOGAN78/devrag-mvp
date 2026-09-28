# Model Providers Catalog & Metadata

## Level 1: Conceptual Overview

RAGFlow supports 40+ model providers across multi-modal categories (Chat, Embedding, Rerank, Vision, Speech/ASR, TTS). Metadata for each model (context window size, maximum completion tokens, vision support, pricing) is centrally registered in [rag/llm/model_meta.py](file:///home/logan78/Desktop/ragflow/rag/llm/model_meta.py#L1).

---

## Level 2: Implementation Details

### Provider Registry Enum

Supported providers are enumerated in [rag/llm/__init__.py](file:///home/logan78/Desktop/ragflow/rag/llm/__init__.py#L25-L66):

```python
class SupportedLiteLLMProvider(StrEnum):
    Tongyi_Qianwen = "Tongyi-Qianwen"
    Dashscope = "Dashscope"
    Bedrock = "Bedrock"
    Moonshot = "Moonshot"
    xAI = "xAI"
    DeepInfra = "DeepInfra"
    Groq = "Groq"
    Cohere = "Cohere"
    Gemini = "Gemini"
    DeepSeek = "DeepSeek"
    Nvidia = "NVIDIA"
    TogetherAI = "TogetherAI"
    Anthropic = "Anthropic"
    Ollama = "Ollama"
    ZHIPU_AI = "ZHIPU-AI"
    MiniMax = "MiniMax"
    OpenAI = "OpenAI"
    Azure_OpenAI = "Azure-OpenAI"
    HunYuan = "Tencent Hunyuan"
    # 40+ providers total
```

### Factory Default API Base URLs

Default API base URLs are defined in [rag/llm/__init__.py](file:///home/logan78/Desktop/ragflow/rag/llm/__init__.py#L68-L100):

```python
FACTORY_DEFAULT_BASE_URL = {
    SupportedLiteLLMProvider.Tongyi_Qianwen: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    SupportedLiteLLMProvider.DeepSeek: "https://api.deepseek.com/v1",
    SupportedLiteLLMProvider.Moonshot: "https://api.moonshot.cn/v1",
    SupportedLiteLLMProvider.SILICONFLOW: "https://api.siliconflow.cn/v1",
    SupportedLiteLLMProvider.OpenRouter: "https://openrouter.ai/api/v1",
    SupportedLiteLLMProvider.ZHIPU_AI: "https://open.bigmodel.cn/api/paas/v4",
    SupportedLiteLLMProvider.OpenAI: "https://api.openai.com/v1",
    # ...
}
```

### Model Metadata Registry

In [rag/llm/model_meta.py](file:///home/logan78/Desktop/ragflow/rag/llm/model_meta.py#L1):

| Metadata Property | Type | Description |
| :--- | :--- | :--- |
| `max_tokens` | `int` | Maximum combined context window limit |
| `max_completion_tokens` | `int` | Maximum generation tokens allowed in a single turn |
| `is_vision` | `bool` | Indicates whether the model supports image/vision inputs |
| `input_price` | `float` | Token cost per 1M prompt tokens |
| `output_price` | `float` | Token cost per 1M completion tokens |

---

### Database Schema for Provider Integration

The `tenant_llm` table ([db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)) persists encrypted provider credentials:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `tenant_id` | `VARCHAR(32)` | Tenant ownership FK |
| `llm_factory` | `VARCHAR(128)` | Provider name (e.g. OpenAI, Ollama, DeepSeek) |
| `model_type` | `VARCHAR(32)` | Capability type: `CHAT`, `EMBEDDING`, `RERANK`, `SPEECH2TEXT`, `TTS` |
| `api_key` | `VARCHAR(255)` | Encrypted API key credentials |
| `api_base` | `VARCHAR(255)` | Custom endpoint URL or proxy base |
