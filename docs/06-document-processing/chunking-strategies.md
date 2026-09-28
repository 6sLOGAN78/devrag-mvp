# Chunking Strategies Reference

## Level 1: Conceptual Overview

RAGFlow provides domain-specific chunking strategies tuned for different document formats, layout structures, and downstream RAG application requirements.

---

## Level 2: Implementation Details

### Configuration Options (`parser_config`)

Configured per dataset or document in `Document.parser_config` JSON field in [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L894):

```json
{
  "pages": [[1, 1000]],
  "chunk_token_num": 512,
  "delimiter": "\n!?;。",
  "table_context_size": 2,
  "image_context_size": 1
}
```

### Strategy Summary Matrix

| Strategy | Target Document Types | Key Delimiters / Boundaries | Code Link |
| :--- | :--- | :--- | :--- |
| **Naive** | Generic Articles / Specs | Custom regex delimiters (`\n\n`, `!`, `?`) | [rag/app/naive.py](file:///home/logan78/Desktop/ragflow/rag/app/naive.py#L30) |
| **Paper** | Academic Journals / IEEE | Section headers (`Abstract`, `1. Introduction`) | [rag/app/paper.py](file:///home/logan78/Desktop/ragflow/rag/app/paper.py#L25) |
| **Book** | PDF / EPUB E-books | Markdown headings (`#`, `##`, `###`) | [rag/app/book.py](file:///home/logan78/Desktop/ragflow/rag/app/book.py#L25) |
| **Laws** | Statutes / Legal Contracts | Articles, Chapters (`第一章`, `第一条`) | [rag/app/laws.py](file:///home/logan78/Desktop/ragflow/rag/app/laws.py#L25) |
| **Presentation** | PPT / Keynote | Slide index boundaries | [rag/app/presentation.py](file:///home/logan78/Desktop/ragflow/rag/app/presentation.py#L20) |
| **Table** | Excel / Financial Data | HTML table rows (`<tr>...</tr>`) | [rag/app/table.py](file:///home/logan78/Desktop/ragflow/rag/app/table.py#L20) |
| **QA** | Q&A FAQs / Customer Support | Question-Answer key pairs | [rag/app/qa.py](file:///home/logan78/Desktop/ragflow/rag/app/qa.py#L25) |
| **Resume** | CV / Resumes | Entities (Work History, Education, Skills) | [rag/app/resume.py](file:///home/logan78/Desktop/ragflow/rag/app/resume.py#L30) |
