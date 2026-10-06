# Knowledge Base UI Studio

## Level 1: Dataset Management Capabilities

The Knowledge Base (Dataset) Studio allows users to manage document collections, configure parsing methods, inspect chunk extraction quality, run hybrid vector search tests, and edit metadata.

---

## Level 2: Component Hierarchy & Source Map

```
web/src/pages/datasets/ & dataset/
├── Datasets Gallery (pages/datasets/index.tsx)
│   ├── Create Dataset Modal (components/create-dataset-dialog)
│   └── Dataset Card Grid (dataset-card.tsx)
└── Dataset Workspace (pages/dataset/index.tsx)
    ├── Document List Tab (dataset-files.tsx)
    │   ├── Document Table Grid
    │   ├── Document Upload Modal (components/file-upload-dialog)
    │   ├── Parse Strategy Configurator (components/parse-configuration)
    │   └── Chunk Status Badge (parsed / chunking / error)
    ├── Parsed Chunks Inspector (pages/chunk/index.tsx)
    │   ├── Side-by-Side Original Document Viewer (document-preview/)
    │   └── Chunk Text & Vector Representation Editor
    └── Retrieval Testing Playground (pages/dataset/testing/index.tsx)
        ├── Similarity Score Slider (similarity-slider/)
        ├── Hybrid Search Query Input
        └── Retrieval Hit Results List
```

### Source Reference Matrix

- Dataset List Page: [`web/src/pages/datasets/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/datasets)
- Dataset Workspace: [`web/src/pages/dataset/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/dataset)
- Chunk Visualizer: [`web/src/pages/chunk/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/chunk)
- Retrieval Testing Page: [`web/src/pages/dataset/testing/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/dataset/testing)
- Document API Hook: [`web/src/hooks/use-document-request.ts`](file:///home/logan78/Desktop/ragflow/web/src/hooks/use-document-request.ts)
- Dataset API Hook: [`web/src/hooks/use-knowledge-request.ts`](file:///home/logan78/Desktop/ragflow/web/src/hooks/use-knowledge-request.ts)
