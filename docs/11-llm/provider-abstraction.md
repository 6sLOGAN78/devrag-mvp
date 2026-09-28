# Provider Abstraction Layer

## Level 1: Conceptual Overview

The **Provider Abstraction Layer** in RAGFlow allows standard application code to interact with over 40 distinct LLM vendors through unified abstract base classes. It bridges vendor-specific APIs (such as OpenAI REST endpoints, Anthropic Messages API, Ollama local REST endpoints, and DashScope native protocol) into consistent Python and Go driver signatures.

```mermaid
graph TD
    App[DialogService / Canvas Component] --> BaseDriver[Base Abstract Driver (chat_model.py)]
    
    BaseDriver --> LiteLLMBase[LiteLLMBase Adapter]
    BaseDriver --> DirectDriver[Direct Driver Subclasses]
    
    LiteLLMBase --> OpenAIDriver[OpenAI / Azure / DeepSeek]
    LiteLLMBase --> AnthropicDriver[Anthropic / Kimi]
    LiteLLMBase --> OllamaDriver[Ollama Local Engine]
    
    DirectDriver --> BaiduDriver[Baidu Yiyan SDK]
    DirectDriver --> SparkDriver[iFlyTek Spark WS]
    DirectDriver --> VolcEngineDriver[VolcEngine Doubao]
```

---

## Level 2: Implementation Details

### Primary Abstraction Classes

#### 1. `Base(ABC)` in [chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L224)
The root interface for all Python chat drivers. Defines model invocation signatures:

```python
class Base(ABC):
    def __init__(self, key, model_name, base_url=None, **kwargs): ...
    
    def chat(self, system, history, gen_conf): ...
    def async_chat(self, system, history, gen_conf): ...
    def chat_streamly(self, system, history, gen_conf): ...
    def async_chat_streamly(self, system, history, gen_conf): ...
```

#### 2. `LiteLLMBase(ABC)` in [chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L1635)
Provides unified completion using the LiteLLM library, mapping provider names from `SupportedLiteLLMProvider` ([rag/llm/__init__.py](file:///home/logan78/Desktop/ragflow/rag/llm/__init__.py#L25)). Handles token streaming, parameter filtering (`ALLOWED_GEN_CONF_KEYS`), and thinking/reasoning control injection (e.g. `enable_thinking` for Qwen or `thinking` for Anthropic/Kimi).

```python
class LiteLLMBase(ABC):
    _FACTORY_NAME = ""

    def __init__(self, key, model_name, base_url=None, **kwargs):
        self.key = key
        self.model_name = model_name
        self.base_url = base_url or FACTORY_DEFAULT_BASE_URL.get(self._FACTORY_NAME)
        # Prefix model name with provider for LiteLLM routing
        self.litellm_model = f"{LITELLM_PROVIDER_PREFIX.get(self._FACTORY_NAME)}/{self.model_name}"
```

#### 3. Error Translation & `LLMErrorCode`
All underlying provider SDK exceptions (HTTP 429, 401, 500, timeouts) are mapped to standardized `LLMErrorCode` enums ([chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L44-L57)):

| Error Code | Enum Member | Retryable |
| :--- | :--- | :--- |
| `RATE_LIMIT_EXCEEDED` | `LLMErrorCode.ERROR_RATE_LIMIT` | Yes |
| `AUTH_ERROR` | `LLMErrorCode.ERROR_AUTHENTICATION` | No |
| `INVALID_REQUEST` | `LLMErrorCode.ERROR_INVALID_REQUEST` | No |
| `TIMEOUT` | `LLMErrorCode.ERROR_TIMEOUT` | Yes |
| `CONTENT_FILTERED` | `LLMErrorCode.ERROR_CONTENT_FILTER` | No |

---

### Generation Call Chain & Retry Engine

```
[LiteLLMBase.async_chat] (rag/llm/chat_model.py#L1700)
   │
   ▼
[Sanitize Parameters] (ALLOWED_GEN_CONF_KEYS check)
   │
   ▼
[litellm.acompletion]
   │
   ├─► Success: Extract response text & usage token metrics
   │
   └─► Exception: Map to LLMErrorCode -> Raise ModelException(retryable=...)
```
