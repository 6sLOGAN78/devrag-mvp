# External Chat Channels & Enterprise Messaging Integrations

## Level 1: Conceptual Overview

RAGFlow natively integrates with 8 major enterprise and consumer chat messaging platforms:
- **Enterprise Platforms**: Feishu / Lark, DingTalk, WeChat Work (WeCom)
- **Global Messaging Bots**: Discord, Telegram, LINE, WhatsApp, QQ Bot

The channel subsystem continuously reconciles active channel bots from the `chat_channel` table without requiring API server restarts. Inbound webhooks or long-polling bot sockets process incoming user messages, trigger RAG completions, and post responses back to chat channels.

---

## Level 2: Implementation Details

### Source File Map

| Messaging Channel | Python Implementation | Go Implementation |
| :--- | :--- | :--- |
| **Channel Manager** | [api/channels/bootstrap.py](file:///home/logan78/Desktop/ragflow/api/channels/bootstrap.py#L17) | [bootstrap.go](file:///home/logan78/Desktop/ragflow/internal/channels/bootstrap.go#L1) |
| **Feishu / Lark** | [api/channels/feishu/channel.py](file:///home/logan78/Desktop/ragflow/api/channels/feishu/channel.py#L1) | [feishu.go](file:///home/logan78/Desktop/ragflow/internal/channels/feishu.go#L1) |
| **DingTalk** | [api/channels/dingtalk/channel.py](file:///home/logan78/Desktop/ragflow/api/channels/dingtalk/channel.py#L1) | [dingtalk.go](file:///home/logan78/Desktop/ragflow/internal/channels/dingtalk.go#L1) |
| **WeCom** | [api/channels/wecom/channel.py](file:///home/logan78/Desktop/ragflow/api/channels/wecom/channel.py#L1) | [wecom.go](file:///home/logan78/Desktop/ragflow/internal/channels/wecom.go#L1) |
| **Discord** | [api/channels/discord/channel.py](file:///home/logan78/Desktop/ragflow/api/channels/discord/channel.py#L1) | [discord.go](file:///home/logan78/Desktop/ragflow/internal/channels/discord.go#L1) |
| **Telegram** | [api/channels/telegram/channel.py](file:///home/logan78/Desktop/ragflow/api/channels/telegram/channel.py#L1) | [telegram.go](file:///home/logan78/Desktop/ragflow/internal/channels/telegram.go#L1) |
| **LINE** | [api/channels/line/channel.py](file:///home/logan78/Desktop/ragflow/api/channels/line/channel.py#L1) | [line.go](file:///home/logan78/Desktop/ragflow/internal/channels/line.go#L1) |
| **WhatsApp** | [api/channels/whatsapp/channel.py](file:///home/logan78/Desktop/ragflow/api/channels/whatsapp/channel.py#L1) | [whatsapp.go](file:///home/logan78/Desktop/ragflow/internal/channels/whatsapp.go#L1) |
| **QQ Bot** | [api/channels/qqbot/channel.py](file:///home/logan78/Desktop/ragflow/api/channels/qqbot/channel.py#L1) | [qqbot.go](file:///home/logan78/Desktop/ragflow/internal/channels/qqbot.go#L1) |

---

### Channel Reconciliation Loop (`bootstrap.py`)

In [api/channels/bootstrap.py](file:///home/logan78/Desktop/ragflow/api/channels/bootstrap.py#L48-L95):

```python
_RECONCILE_INTERVAL_SECS = 10

def _desired_channels() -> dict:
    """Queries chat_channel table for active bot credentials and computes configuration fingerprints."""
    desired = {}
    for row in ChatChannelService.list_active():
        credential = (row.config or {}).get("credential", {})
        desired[row.id] = (row.channel, credential, _fingerprint(row.channel, credential))
    return desired
```

1. Every 10 seconds, `bootstrap.py` checks active rows in `chat_channel`.
2. New bots are instantiated and launched in background tasks.
3. Removed or modified bots (detected by fingerprint hash mismatches) are safely stopped and reloaded without dropping unrelated active bots.
