# Important Concepts in RAGFlow

## 1. Vision-Based DeepDoc Parsing
Unlike traditional RAG systems that rely solely on text extraction, RAGFlow uses **DeepDoc**, a computer vision and layout analysis engine. DeepDoc detects visual bounding boxes for document elements (titles, paragraphs, headers, footers, tables, figures) using YOLO models, executes OCR via PaddleOCR, and reconstructs table HTML structures.

- **Primary Source**: [deepdoc/parser/pdf_parser.py](file:///home/logan78/Desktop/ragflow/deepdoc/parser/pdf_parser.py#L50) & [deepdoc/vision/layout_recognizer.py](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py#L30).

---

## 2. Multi-Parser Chunking Strategies
RAGFlow supports specialized chunking templates based on document domain (`parser_id`):
- **Naive / Manual**: Split text by sentence boundaries and length limits.
- **QA**: Generate question-answer pairs directly from document text.
- **Resume**: Parse structured resumes into skills, work experience, and education blocks.
- **Paper / Laws**: Extract section headers, articles, and legal clauses.
- **Table / Presentation**: Preserve full rows/columns and slide layouts.


---

## 3. Hybrid Search & Reranking Engine
RAGFlow combines two complementary search paradigms:
1. **Sparse BM25 Keyword Search**: Exact term matching enriched by synonym expansion (`content_ltks`).
2. **Dense Vector Similarity Search**: Semantic vector matching using cosine similarity (`q_{dim}_vec`).

Candidate chunks from both searches are combined and re-scored using cross-encoder rerankers (e.g. `bge-reranker-large`).

- **Primary Source**: [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L134).

---

## 4. RAPTOR Hierarchical Summarization
RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval) recursively clusters small text chunks using Gaussian Mixture Models (GMM) or K-Means and generates higher-level summary chunks via LLM calls. This allows RAGFlow to answer high-level holistic questions across entire documents.

- **Primary Source**: [rag/utils/raptor_utils.py](file:///home/logan78/Desktop/ragflow/rag/utils/raptor_utils.py#L48).

---

## 5. Agent Canvas DAG Execution
Agent Canvas compiles a user-designed visual flow into a Directed Acyclic Graph (DAG) of component nodes. State context is passed down graph edges, and node progress is streamed in real time via Server-Sent Events.

- **Primary Source**: [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L49).
