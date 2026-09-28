# Document Upload & Parser UI

## Level 1: Document Processing Workflow

The Document Upload and Parsing UI provides a guided step-by-step pipeline for importing multi-format documents into RAGFlow knowledge bases.

---

## Level 2: Component Breakdown & Source Links

### 1. Document Upload Dialog ([`components/file-upload-dialog`](file:///home/logan78/Desktop/ragflow/web/src/components/file-upload-dialog))
- Drag-and-drop file upload container supporting PDF, DOCX, PPTX, XLSX, TXT, MD, CSV, JPG, PNG, MP3, WAV.
- Performs client-side validation (file extension white-list, max content size limits).

### 2. Chunking Method Selection Dialog ([`components/chunk-method-dialog`](file:///home/logan78/Desktop/ragflow/web/src/components/chunk-method-dialog))
- Allows users to select document-specific parsing models:
  - `General`: Paragraph-based chunking with layout recognition.
  - `Q&A`: Extracting structured question-answer pairs.
  - `Paper`: Academic paper layout recognition (abstract, sections, references).
  - `Manual`: Technical manual chunking.
  - `Law`: Legal document hierarchy chunking.
  - `Table`: Visual table structure extraction (TSR).
  - `Book`: Deep chapter hierarchy chunking.

### 3. Parser Parameter Configurator ([`components/parse-configuration`](file:///home/logan78/Desktop/ragflow/web/src/components/parse-configuration))
- Customization controls: `chunk_token_num` (default 128-512), `delimiter` regex, visual layout vision model toggle, auto-keyword extraction count.

### 4. Document Status Monitoring
- Displays real-time chunking progress bars, task execution status badges (UNSTART, RUNNING, SUCCESS, FAIL), and error trace logs.

### Source References

- File Upload Dialog: [`web/src/components/file-upload-dialog/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/components/file-upload-dialog)
- Chunking Method Selector: [`web/src/components/chunk-method-dialog/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/components/chunk-method-dialog)
- Document Hook: [`web/src/hooks/use-document-request.ts`](file:///home/logan78/Desktop/ragflow/web/src/hooks/use-document-request.ts)
