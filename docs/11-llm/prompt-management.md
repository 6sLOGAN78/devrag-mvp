# Prompt Template Management & Function Calling

## Level 1: Conceptual Overview

**Prompt Management** in RAGFlow provides system prompt compilation, context variable interpolation (`{knowledge_base}`, `{chat_history}`, `{user_query}`), prompt template persistence, and function/tool schema generation for ReAct or JSON tool calling.

---

## Level 2: Implementation Details

### Source File Map
- **Prompt Generators**: [rag/prompts/generator.py](file:///home/logan78/Desktop/ragflow/rag/prompts/generator.py)
- **Prompt Templates**: [rag/prompts/template.py](file:///home/logan78/Desktop/ragflow/rag/prompts/template.py)
- **Tool Decorator**: [rag/llm/tool_decorator.py](file:///home/logan78/Desktop/ragflow/rag/llm/tool_decorator.py)

---

### Function Tool Session & Schema Decorator

In [rag/llm/tool_decorator.py](file:///home/logan78/Desktop/ragflow/rag/llm/tool_decorator.py):

Functions annotated with `@is_tool` are reflected into OpenAI-compatible JSON Schema tools definitions:

```python
class FunctionToolSession:
    """Manages registered tool functions and converts Python docstrings and parameter
    type hints into JSON schema function call signatures."""
    
    def register_tool(self, func): ...
    def get_tools_schema(self) -> list[dict]: ...
```

Generated Tool Definition Format:
```json
{
  "type": "function",
  "function": {
    "name": "google_search",
    "description": "Performs web search query via Google",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "Search term"}
      },
      "required": ["query"]
    }
  }
}
```

---

### Knowledge Chunk Prompt Formatting (`chunks_format`)

Retrieved knowledge chunks are formatted into systemic prompt blocks using standard markdown sectioning ([generator.py](file:///home/logan78/Desktop/ragflow/rag/prompts/generator.py)):

```python
def chunks_format(chunks: list[dict]) -> str:
    """Formats retrieved vector/keyword chunks into prompt text with inline ID tags."""
    formatted = []
    for idx, c in enumerate(chunks):
        formatted.append(f"Document [{idx + 1}]: {c['doc_name']}\n{c['content_with_weight']}")
    return "\n\n".join(formatted)
```
