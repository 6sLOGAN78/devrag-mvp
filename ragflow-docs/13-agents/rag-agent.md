# Specialized RAG Agent Implementation

## Level 1: Conceptual Overview

The **RAG Agent** (`rag_agent`) is a specialized agent preset that optimizes Knowledge Base document retrieval, query rewriting, multi-document synthesis, and citation generation. It can be invoked directly as a solo dialog handler or as a component node within canvas agent workflows.

---

## Level 2: Implementation Details

### Source File Map
- **Dialog Service RAG Agent**: [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L700-L800)
- **Retrieval Component**: [agent/tools/retrieval.py](file:///home/logan78/Desktop/ragflow/agent/tools/retrieval.py#L1)

---

### Implementation Details (`rag_agent` Function)

In [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L720):

```python
async def rag_agent(dialog, messages, stream=True, **kwargs):
    """Specialized RAG agent flow with iterative query rewriting and multi-KB retrieval."""
    user_query = messages[-1]["content"]
    
    # 1. Query Rewrite Step (if enabled)
    rewritten_queries = await rewrite_query(user_query, dialog.llm_id)
    
    # 2. Parallel Vector & Hybrid Retrieval across linked KBs
    retrieved_chunks = await search_kbs(rewritten_queries, dialog.kb_ids)
    
    # 3. Rerank & Context Assembly
    ranked_chunks = rerank_service.similarity(user_query, retrieved_chunks)
    context_str = chunks_format(ranked_chunks)
    
    # 4. LLM Generation with Citation Annotation (##0$$)
    async for token in llm_bundle.async_chat_streamly(system_prompt, messages, gen_conf):
        yield token
```
