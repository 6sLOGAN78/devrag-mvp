# Part 08: Advanced DeepDoc

## 5.1 Part Objective
This part upgrades the Document Ingestion pipeline (Part 05) to handle complex unstructured formats like PDFs, PPTs, and images. It replaces the naive text chunker with a Computer Vision pipeline that uses YOLO for layout analysis (detecting tables vs paragraphs vs images) and PaddleOCR for text extraction. This is the defining feature of RAGFlow.

*Relevant Docs*: `docs/06-document-processing/parsers.md`, `docs/06-document-processing/vision-models.md`.

## 5.2 Prerequisites
*   **Required previous parts**: `Part-05-Document-Ingestion` (The worker infrastructure).
*   **Required infrastructure**: A machine with sufficient CPU/RAM (or a GPU) to run deep learning models locally, OR an external API serving these models.

## 5.3 Internal Subparts
*   **`01-PDF-to-Image`**: Rasterizing documents into images.
*   **`02-Layout-Analysis`**: Running YOLO to draw bounding boxes.
*   **`03-OCR-and-TSR`**: Running PaddleOCR and Table Structure Recognition to extract text/markdown.

## 5.4 Overall Data Flow
```mermaid
flowchart TD
    S3[S3 Blob] -->|Download| P2I[PDF to Image Rasterizer]
    P2I -->|Images| YOLO[YOLO Layout Model]
    YOLO -->|Bounding Boxes| CROP[Image Cropper]
    
    CROP -->|Table Image| TSR[Table Structure Recognition]
    CROP -->|Text Image| OCR[PaddleOCR]
    
    TSR -->|Markdown Grid| MERGE[Content Merger]
    OCR -->|Raw Text| MERGE
    
    MERGE -->|Array of Chunks| EMBED[Embedding API (Part 05)]
```

## 5.5 Overall Implementation Order
Sequential. You cannot analyze a PDF without rasterizing it (01). You cannot run OCR without knowing where the text blocks are (02). Once text is extracted (03), it hands off to the existing embedding pipeline.

## 5.6 Expected Final Result
*   Uploading a highly visual PDF (e.g., a scientific paper with 2 columns and tables) results in clean, separated chunks of text and markdown tables in the Vector DB, without garbled text crossing column boundaries.

## 5.7 Scope Exclusions
*   Multimodal LLMs (sending images directly to GPT-4o for parsing) are excluded here, as DeepDoc relies on local specialized vision models to save costs.

## 5.8 Documentation References
*   `docs/06-document-processing/parsers.md`
*   `docs/06-document-processing/vision-models.md`
