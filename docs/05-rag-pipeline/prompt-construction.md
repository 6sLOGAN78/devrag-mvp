# Prompt Construction Subsystem

## Level 1: Conceptual Overview

Prompt Construction combines conversation history, system directives, dynamic user parameters, and retrieved context blocks into a structured prompt payload sent to LLMs.

---

## Level 2: Implementation Details

### Dialog System Configuration

Dialog parameters are stored in `Dialog` model in [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L1020-L1050):

- `prompt_type`: `"simple"` vs `"advanced"`
- `prompt_config`: JSON configuration containing system instructions, prologue, parameters, and empty response fallbacks.

```json
{
  "system": "You are a helpful assistant. Please answer the user question based strictly on the provided context.",
  "prologue": "Hi! I'm your assistant. What can I do for you?",
  "empty_response": "Sorry! No relevant content was found in the knowledge base!"
}
```

### Prompt Generation Pipeline

Prompt generation routines live in [rag/prompts/generator.py](file:///home/logan78/Desktop/ragflow/rag/prompts/generator.py#L15):
- `keyword_extraction`: Generates keyword extraction prompts.
- `question_proposal`: Generates follow-up question proposals.
- `content_tagging`: Generates document metadata tag classification prompts.
- `gen_metadata`: Auto-generates document JSON Schema metadata.
