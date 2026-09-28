# Multi-Provider Model Integrations

## Level 1: Conceptual Overview

RAGFlow integrates with over 40 model providers across 6 multi-modal task types (Chat, Embeddings, Reranking, Vision/OCR, ASR, TTS). Provider drivers manage encrypted tenant credentials, custom base URLs, proxy routing, token rate limits, and fallback retries.

---

## Level 2: Implementation Details

### Source File Map
- **Provider Enum & Base URLs**: [rag/llm/__init__.py](file:///home/logan78/Desktop/ragflow/rag/llm/__init__.py#L25-L100)
- **Chat Drivers**: [rag/llm/chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L224)
- **Embedding Drivers**: [rag/llm/embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L146)
- **Rerank Drivers**: [rag/llm/rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L32)
- **Go Model Service**: [internal/service/model_service.go](file:///home/logan78/Desktop/ragflow/internal/service/model_service.go#L38-L100)

---

### Key Provider Categories

1. **Global Cloud API Providers**: OpenAI, Azure OpenAI, Anthropic, Google Gemini, AWS Bedrock, Cohere, Groq, TogetherAI, OpenRouter.
2. **Domestic Chinese AI Platforms**: Tongyi Qianwen / DashScope, Zhipu AI, DeepSeek, Moonshot, Baidu Yiyan, Tencent Hunyuan, StepFun, SiliconFlow, 01.AI.
3. **Local Self-Hosted Runtimes**: Ollama, LocalAI, Xinference, LM Studio, GPUStack, HuggingFace Transformers.
