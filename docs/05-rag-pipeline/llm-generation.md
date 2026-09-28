# LLM Generation Subsystem

## Level 1: Conceptual Overview

The LLM Generation subsystem streams tokens from language models back to user interfaces or API clients while enforcing token budgets, rate limits, temperature controls, and stop sequences.

---

## Level 2: Implementation Details

### LLM Bundle & Factory Architecture

Implemented in `api/db/services/llm_service.py` (`LLMBundle`) and `rag/llm/chat_model.py`.

Supported LLM Providers:
- OpenAI (GPT-4o, GPT-3.5)
- Anthropic (Claude 3.5 Sonnet)
- Qwen / DashScope
- Ollama / Local vLLM
- DeepSeek (DeepSeek V3 / R1)
- Zhipu GLM / Baidu Yiyan / Baichuan / Moonshot

### Streaming Response Execution


```python
async def completion():
    # 1. Resolve LLM configuration from Tenant Model
    llm_bundle = LLMBundle(tenant_id, LLMType.CHAT, llm_name)
    # 2. Stream generation delta events
    for chunk in llm_bundle.chat_stream(messages, gen_conf):
        yield f"data: {json.dumps(chunk)}\n\n"
```
