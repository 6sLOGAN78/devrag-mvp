# Conversation Memory & Context Truncation

## Level 1: Conceptual Overview

**Conversation Memory** prevents prompt overflow errors when multi-turn dialogues exceed the chosen LLM's maximum token context window (`max_tokens`). It truncates historic conversation turns using token-based rolling windows while retaining the static system prompt and newly retrieved knowledge context.

---

## Level 2: Implementation Details

### Source File Map
- **Token Utilities**: [common/token_utils.py](file:///home/logan78/Desktop/ragflow/common/token_utils.py#L1)
- **Dialog Core Engine**: [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L500-L580)

---

### Context Truncation Strategy

```
[System Prompt + Knowledge Chunks] (Static Priority)
   +
[Turn N-2] (Oldest) ---> Truncated if budget exceeded
   +
[Turn N-1]          ---> Kept if within budget
   +
[Turn N (User Query)] (Highest Priority)
```

In [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L520-L560):

```python
# Calculate token budget remaining for conversation history
system_tokens = num_tokens_from_string(system_prompt)
knowledge_tokens = num_tokens_from_string(knowledge_context)
budget = max_tokens - system_tokens - knowledge_tokens - max_completion_tokens - SAFETY_MARGIN

# Rolling window from newest turn to oldest turn
history_tokens = 0
truncated_history = []
for msg in reversed(messages[:-1]):
    t = num_tokens_from_string(msg["content"])
    if history_tokens + t > budget:
        break
    truncated_history.insert(0, msg)
    history_tokens += t
```
