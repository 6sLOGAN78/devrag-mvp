# Context Construction & Citation Indexing

## Level 1: Conceptual Overview

**Context Construction** formats retrieved vector and keyword chunks, system prompt templates, metadata filters, and historical turn messages into a single prompt payload for the LLM. It embeds citation tags (`##0$$`, `##1$$`) directly into context blocks so generated answers explicitly cite source document chunks.

---

## Level 2: Implementation Details

### Source File Map
- **Prompt Generator**: [rag/prompts/generator.py](file:///home/logan78/Desktop/ragflow/rag/prompts/generator.py#L1)
- **Dialog Service**: [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L400-L550)

---

### Citation Formatting Algorithm (`##0$$`)

In [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L450-L500):

```
Chunk 0 -> Doc: "Contract.pdf" (Page 3) -> Token Tag: ##0$$
Chunk 1 -> Doc: "Policy.docx" (Page 1) -> Token Tag: ##1$$
```

1. **Context Assembly**: Each chunk's text is formatted with a distinct bracket tag `[ID: n]`.
2. **LLM Generation**: System prompt instructs the model: *"Cite source chunks using ##n$$ notation."*
3. **Reference Map Assembly**:
   ```json
   {
     "chunks": [
       {"id": "c0", "doc_name": "Contract.pdf", "doc_id": "d1", "content": "..."},
       {"id": "c1", "doc_name": "Policy.docx", "doc_id": "d2", "content": "..."}
     ],
     "total": 2
   }
   ```
4. **Front-End Rendering**: The Web UI parses `##0$$` markers into interactive tooltips displaying source document previews.
