# 11-LLM: Subsystem Overview & Architecture

## Level 1: Conceptual Overview

The **LLM Subsystem** in RAGFlow abstracts text generation, vector embeddings, cross-encoder reranking, optical character recognition (OCR/CV), speech-to-text (ASR), and text-to-speech (TTS) across 40+ cloud and open-source model providers. It isolates downstream business logic (Chat, Agent Workflows, RAG Indexing) from vendor-specific API formats, token limits, rate-limit retries, and authentication mechanisms.

```mermaid
graph TD
    App[RAG App / Dialog Service / Workflows / Canvas] --> LLMBundle[LLMBundle (llm_service.py)]
    LLMBundle --> ModelFactory[Model Factory & Provider Resolution]
    
    ModelFactory --> ChatProvider[Chat Models (chat_model.py)]
    ModelFactory --> EmbedProvider[Embedding Models (embedding_model.py)]
    ModelFactory --> RerankProvider[Rerank Models (rerank_model.py)]
    ModelFactory --> VisionProvider[Vision / OCR Models (cv_model.py, ocr_model.py)]
    ModelFactory --> ASRProvider[ASR / Speech Models (sequence2txt_model.py)]
    ModelFactory --> TTSProvider[TTS Models (tts_model.py)]
    
    ChatProvider --> LiteLLM[LiteLLM Provider Abstraction (LiteLLMBase)]
    ChatProvider --> DirectSDK[Direct SDK Adapters (OpenAI, Ollama, DashScope, Zhipu)]
    
    LLMBundle --> LangfuseObs[Langfuse Observation & Token Accounting]
    ModelFactory --> GoModelService[Go Port Model Service (model_service.go)]
```

### Core Objectives
1. **Multi-Tenant Provider Management**: Encrypt and store API keys per tenant (`tenant_llm`), allowing users to configure custom API base URLs, proxy settings, and model aliases.
2. **Unified Driver Interface**: Provide standard interfaces (`chat`, `async_chat`, `embedding`, `similarity`, `tts`) so business services invoke LLMs without provider-specific logic.
3. **Robust Token Accounting & Telemetry**: Track prompt/completion token usage across streaming and non-streaming calls, propagating metrics to Langfuse observations and task run records.
4. **Dual Engine Synchronization**: Parity between Python drivers ([chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L224)) and Go model resolution services ([model_service.go](file:///home/logan78/Desktop/ragflow/internal/service/model_service.go#L38-L100)).

---

## Level 2: Implementation Details

### Source File Map

| Component | Source Path | Primary Purpose |
| :--- | :--- | :--- |
| **Provider Registry & Defaults** | [rag/llm/__init__.py](file:///home/logan78/Desktop/ragflow/rag/llm/__init__.py#L25-L100) | `SupportedLiteLLMProvider` enum, `FACTORY_DEFAULT_BASE_URL` dictionary |
| **Chat Model Abstraction** | [rag/llm/chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L224) | `Base`, `LiteLLMBase`, `LLMErrorCode`, streaming sanitizers, tool wrappers |
| **Embedding Abstraction** | [rag/llm/embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L146) | `Base`, `OpenAIEmbed`, `QWenEmbed`, `OllamaEmbed`, batch token truncation |
| **Rerank Abstraction** | [rag/llm/rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L32) | `Base`, `JinaRerank`, `NvidiaRerank`, `_normalize_rank` min-max mapping |
| **Model Metadata Registry** | [rag/llm/model_meta.py](file:///home/logan78/Desktop/ragflow/rag/llm/model_meta.py#L1) | Token window limits, vision capabilities, cost calculations |
| **LLM Bundle Service** | [api/db/services/llm_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py#L37) | `LLMBundle` class resolving tenant credentials and instantiating drivers |
| **Go Model Resolver** | [internal/service/model_service.go](file:///home/logan78/Desktop/ragflow/internal/service/model_service.go#L50-L100) | `parseModelName`, composite model key resolution (`model@instance@provider`) |

---

### Core Data Structures & Driver Factory

#### 1. Composite Model ID Resolution
Model identifiers in RAGFlow are formatted as composite strings to distinguish provider backends and tenant custom instances:
`model_name@instance_name@provider_name` or `model_name@provider_name`

In Python ([llm_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py#L37)):
```python
# TenantLLMService resolves credentials by tenant_id and composite llm_name
tenant_llm = TenantLLMService.get_api_key(tenant_id, llm_name)
```

In Go ([model_service.go](file:///home/logan78/Desktop/ragflow/internal/service/model_service.go#L50-L67)):
```go
func parseModelName(compositeName string) (modelName, instanceName, providerName string, err error) {
	parts := strings.Split(compositeName, "@")
	switch len(parts) {
	case 3:
		return parts[0], parts[1], parts[2], nil
	case 2:
		return parts[0], "default", parts[1], nil
	...
	}
}
```

#### 2. LLMBundle Lifecycle
`LLMBundle` ([llm_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py#L37)) wraps model instantiation, error handling, token accounting, and Langfuse tracing.

```
Caller (Dialog/Agent) -> LLMBundle(tenant_id, model_config)
    |-> TenantLLMService.get_api_key(...)
    |-> Instantiate Driver (e.g. LiteLLMBase / OpenAIEmbed)
    |-> chat() / async_chat()
          |-> _reset_last_usage()
          |-> driver.chat() / async_chat()
          |-> _report_usage(total_tokens)
          |-> Return response text / stream generator
```

---

### Generation Parameter Filtering

When forwarding generation configurations (`llm_setting`) to underlying drivers, internal keys like `model_type` or `prompt_type` must be purged to prevent provider rejection ([chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L73-L96)):

```python
ALLOWED_GEN_CONF_KEYS = frozenset({
    "temperature", "max_completion_tokens", "top_p", "stream",
    "stream_options", "stop", "n", "presence_penalty",
    "frequency_penalty", "functions", "function_call", "logit_bias",
    "user", "response_format", "seed", "tools", "tool_choice",
    "logprobs", "top_logprobs", "extra_headers"
})
```

---

### Code Call Chain

```
[REST API / Handler]
   │
   ▼
[DialogService.async_chat] (api/db/services/dialog_service.py)
   │
   ▼
[LLMBundle.__init__] (api/db/services/llm_service.py#L37)
   │
   ▼
[TenantLLMService.get_api_key] (api/db/services/tenant_llm_service.py)
   │
   ▼
[LiteLLMBase.__init__ / Base.__init__] (rag/llm/chat_model.py#L1635)
   │
   ▼
[LiteLLMBase.async_chat] (rag/llm/chat_model.py#L1700)
   │  ├── litellm.acompletion()
   │  └── _StreamSanitizer
   ▼
[LLMBundle._report_usage] (api/db/services/llm_service.py#L65)
```
