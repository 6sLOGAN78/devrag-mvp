# Integrations Subsystem Overview

## Level 1: Conceptual Overview

The **Integrations Subsystem** connects RAGFlow with external messaging channels (DingTalk, Feishu/Lark, WeChat Work, Discord, Telegram, LINE, WhatsApp, QQ Bot), vector and hybrid search engines (Infinity, Elasticsearch, OpenSearch, PGVector), object storage systems (MinIO, S3, Azure Blob, OSS), and MCP servers.

```mermaid
graph TD
    RAGFlow[RAGFlow Engine Core] --> MessagingChannels[Chat Channels (api/channels & internal/channels)]
    RAGFlow --> MCPBridge[MCP Server Bridge (internal/mcp)]
    RAGFlow --> ModelProviders[Model Gateways (OpenAI, Ollama, DeepSeek)]
    RAGFlow --> SearchVectorDB[Vector & Search Stores (Infinity, Elasticsearch, OpenSearch)]
    RAGFlow --> ObjectStorage[Object Storage (MinIO, S3, OSS)]
    
    subgraph Multi-Platform Messaging
        MessagingChannels --> Feishu[Feishu / Lark Bot]
        MessagingChannels --> DingTalk[DingTalk Bot]
        MessagingChannels --> WeCom[WeChat Work Bot]
        MessagingChannels --> Telegram[Telegram Bot]
        MessagingChannels --> Discord[Discord Bot]
        MessagingChannels --> WhatsApp[WhatsApp Gateway]
    end
```

---

## Level 2: Implementation Details

### Source File Map

| Integration Area | Python Path | Go Path | Key Responsibilities |
| :--- | :--- | :--- | :--- |
| **Messaging Channels** | [api/channels/bootstrap.py](file:///home/logan78/Desktop/ragflow/api/channels/bootstrap.py#L1) | [bootstrap.go](file:///home/logan78/Desktop/ragflow/internal/channels/bootstrap.go#L1) | Continuous bot reconciliation, inbound webhook handling, message reply |
| **MCP Integration** | — | [connector.go](file:///home/logan78/Desktop/ragflow/internal/mcp/connector.go#L28) | In-process service bridge exposing dataset search & chat assistants |
| **Model Services** | [rag/llm/](file:///home/logan78/Desktop/ragflow/rag/llm/__init__.py#L1) | [model_service.go](file:///home/logan78/Desktop/ragflow/internal/service/model_service.go#L1) | 40+ cloud/local LLM provider API clients |
