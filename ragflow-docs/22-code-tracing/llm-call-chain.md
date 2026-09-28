# LLM Call Chain Tracing

## Level 1: Conceptual Overview

The LLM call chain abstracts model interactions across cloud LLM providers (OpenAI, Anthropic, DashScope/Qwen, DeepSeek, Zhipu, Baidu) and self-hosted models (Ollama, vLLM, LocalAI, LMStudio).

---

## Level 2: Complete Code Call Chain

```
[Service Layer / Agent Canvas / Chat Controller]
       │
       ▼
[api/db/services/llm_service.py:LLMBundle] [L35]
       │
       ├─► Model Initialization:
       │     └─► LLMBundle.__init__(tenant_id, llm_type, llm_name)
       │           └─► TenantModelService.get_model_config() [api/db/joint_services/tenant_model_service.py]
       │
       ├─► Text Vector Embedding Generation:
       │     └─► LLMBundle.encode(texts) [L120]  or  LLMBundle.encode_queries(query)
       │           └─► Factory dispatch to provider class (e.g. OpenAIEmbed, QwenEmbed, HuggingFaceEmbed)
       │
       ├─► Synchronous Chat Generation:
       │     └─► LLMBundle.chat(system_prompt, history, gen_conf) [L180]
       │           └─► Provider API post request -> Parse response -> Return answer string & token count
       │
       ├─► Streaming Chat Generation:
       │     └─► LLMBundle.chat_streamly(system_prompt, history, gen_conf) [L220]
       │           └─► Async yield stream delta tokens
       │
       └─► Token Consumption Sink:
             └─► common/token_utils.py:token_usage_sink()
                   └─► Write token metrics to MySQL table `tenant_token_usage`
```

---

## Provider Factory Dispatch

The `TenantLLM` database model maps model names to provider classes:

| Provider Name | Implementation Class File |
|---|---|

---

## Exact Source Code References

- **LLM Bundle Class**: `LLMBundle` in [api/db/services/llm_service.py:L35](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py#L35)
- **Embedding Dispatcher**: `LLMBundle.encode()` in [api/db/services/llm_service.py:L120](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py#L120)
- **Synchronous Chat Method**: `LLMBundle.chat()` in [api/db/services/llm_service.py:L180](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py#L180)
- **Streaming Chat Method**: `LLMBundle.chat_streamly()` in [api/db/services/llm_service.py:L220](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py#L220)
- **Tenant Model Service**: [api/db/joint_services/tenant_model_service.py:L30](file:///home/logan78/Desktop/ragflow/api/db/joint_services/tenant_model_service.py#L30)
- **Token Tracker**: [common/token_utils.py:L30](file:///home/logan78/Desktop/ragflow/common/token_utils.py#L30)
