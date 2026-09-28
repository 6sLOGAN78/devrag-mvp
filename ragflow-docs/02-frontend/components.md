# Reusable Frontend Components

## Level 1: Component Subsystem Architecture

The reusable UI component library is located under [`web/src/components/`](file:///home/logan78/Desktop/ragflow/web/src/components). It provides standardized interface widgets for document parsing, LLM parameter configuration, markdown rendering, canvas node controls, and modal dialogs.

---

## Level 2: Component Catalog & File Map

### 1. Document & Parsing Components

| Component Name | Source Folder | Purpose & Features |
| :--- | :--- | :--- |
| `chunk-method-dialog` | [`web/src/components/chunk-method-dialog`](file:///home/logan78/Desktop/ragflow/web/src/components/chunk-method-dialog) | Modal for selecting document parsing methods (General, Q&A, Paper, Book, Laws, Presentation, Table, Manual). |
| `parse-configuration` | [`web/src/components/parse-configuration`](file:///home/logan78/Desktop/ragflow/web/src/components/parse-configuration) | Configurator for chunk token size, overlap, layout vision model toggles, and custom delimiting Regex. |
| `document-preview` | [`web/src/components/document-preview`](file:///home/logan78/Desktop/ragflow/web/src/components/document-preview) | Multi-format preview drawer showing highlighted bounding boxes on original PDF pages side-by-side with extracted chunk text. |
| `file-upload-dialog` | [`web/src/components/file-upload-dialog`](file:///home/logan78/Desktop/ragflow/web/src/components/file-upload-dialog) | Drag-and-drop file uploader with file type validation, size checks, and progress bars. |

### 2. Model & Prompt Components

| Component Name | Source Folder | Purpose & Features |
| :--- | :--- | :--- |
| `llm-select` | [`web/src/components/llm-select`](file:///home/logan78/Desktop/ragflow/web/src/components/llm-select) | Dropdown selector for LLM providers (OpenAI, Anthropic, Ollama, DeepSeek, Qwen) and active model instances. |
| `llm-setting-items` | [`web/src/components/llm-setting-items`](file:///home/logan78/Desktop/ragflow/web/src/components/llm-setting-items) | Form sliders for adjusting `temperature`, `top_p`, `presence_penalty`, `frequency_penalty`, and `max_tokens`. |
| `similarity-slider` | [`web/src/components/similarity-slider`](file:///home/logan78/Desktop/ragflow/web/src/components/similarity-slider) | Threshold slider for vector similarity cutoffs (0.0 to 1.0) and vector weight vs BM25 weight ratios. |

### 3. Markdown & Chat Components

| Component Name | Source Folder | Purpose & Features |
| :--- | :--- | :--- |
| `markdown-content` | [`web/src/components/markdown-content`](file:///home/logan78/Desktop/ragflow/web/src/components/markdown-content) | Renders assistant response markdown, supporting code block syntax highlighting, copy-to-clipboard buttons, KaTeX formulas, and image popovers. |
| `message-item` | [`web/src/components/message-item`](file:///home/logan78/Desktop/ragflow/web/src/components/message-item) | Renders user and assistant chat bubbles, citation reference pills, hit scores, and feedback buttons. |
| `message-input` | [`web/src/components/message-input`](file:///home/logan78/Desktop/ragflow/web/src/components/message-input) | Chat input text area with auto-grow, file attachment upload, send button, and stop generation trigger. |

### 4. Agent Canvas Components

| Component Name | Source Folder | Purpose & Features |
| :--- | :--- | :--- |
| `canvas` | [`web/src/components/canvas`](file:///home/logan78/Desktop/ragflow/web/src/components/canvas) | Node handle connectors, custom edge paths, node header controls, and execution status indicators. |
| `structure-graph` | [`web/src/components/structure-graph`](file:///home/logan78/Desktop/ragflow/web/src/components/structure-graph) | Interactive graph visualization for document knowledge graphs and entity connections. |
