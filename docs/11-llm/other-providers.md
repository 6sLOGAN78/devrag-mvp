# Other Model Providers (DeepSeek, Zhipu, Qwen, HuggingFace, etc.)

## Level 1: Conceptual Overview

In addition to OpenAI and Ollama, RAGFlow supports over 35 other model providers, including domestic Chinese AI providers (Tongyi Qianwen/DashScope, Zhipu AI, DeepSeek, Moonshot, Baidu Yiyan, Tencent Hunyuan) and global cloud platforms (Anthropic, Google Gemini, AWS Bedrock, Cohere, Groq, TogetherAI, SiliconFlow).

---

## Level 2: Implementation Details

### Provider-Specific Driver Highlights

#### 1. DeepSeek (`DeepSeek`)
- **Chat Driver**: [chat_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/chat_model.py#L1635) (`LiteLLMBase` mapped to `deepseek/deepseek-chat` or `deepseek/deepseek-reasoner`).
- **Base URL**: `https://api.deepseek.com/v1` ([rag/llm/__init__.py](file:///home/logan78/Desktop/ragflow/rag/llm/__init__.py#L71)).
- **Reasoning Stream Handling**: Supports `<think> ... </think>` block extraction during reasoning outputs from `deepseek-r1`.

#### 2. Tongyi Qianwen / DashScope (`QWenEmbed`, `QWenRerank`)
- **Embedding Driver**: [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L379-L445) (`QWenEmbed`). Converts OpenAI-compatible base URLs (`compatible-mode/v1`) to DashScope native HTTP API roots (`https://dashscope.aliyuncs.com/api/v1`) via `_dashscope_native_http_api_url`.
- **Rerank Driver**: [rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L524) (`QWenRerank`). Scores pairs using DashScope text-rerank endpoint.

#### 3. Zhipu AI / GLM (`ZhipuEmbed`)
- **Embedding Driver**: [embedding_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/embedding_model.py#L446-L477) (`ZhipuEmbed`). Invokes `ZhipuAiClient` using JWT-signed header authentication for models like `embedding-2` and `embedding-3`.
- **Base URL**: `https://open.bigmodel.cn/api/paas/v4` ([rag/llm/__init__.py](file:///home/logan78/Desktop/ragflow/rag/llm/__init__.py#L88)).

#### 4. SiliconFlow & OpenRouter Gateway Providers
