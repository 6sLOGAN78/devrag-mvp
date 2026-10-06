# PDF Processing Pipeline

## Level 1: Conceptual Overview

PDF Processing is the core pipeline of DeepDoc. PDFs present complex challenges: non-linear reading orders, multi-column layouts, embedded raster images, vector line tables, missing text layers (scanned documents), and complex equations.

---

## Level 2: Implementation Details

### Pipeline Execution Steps

Implemented in [deepdoc/parser/pdf_parser.py](file:///home/logan78/Desktop/ragflow/deepdoc/parser/pdf_parser.py#L35) and [internal/deepdoc/parser/pdf/parser.go](file:///home/logan78/Desktop/ragflow/internal/deepdoc/parser/pdf/parser.go#L40):

```mermaid
flowchart TD
    PdfFile[Raw PDF Stream] --> PyMuPDF[PyMuPDF fitz / pdfium Reader]
    PyMuPDF --> TextSpans[Extract Native Text Spans & BBoxes]
    PyMuPDF --> Render[Rasterize Pages to Images zoom=3]
    
    Render --> LayoutEngine[LayoutRecognizer DLA YOLO Model]
    LayoutEngine --> BBoxTypes[Detected Layout Regions: Title, Text, Table, Figure, Header, Footer]
    
    TextSpans & Render --> CheckOCR{Text Layer Present?}
    CheckOCR -->|No / Corrupted| OCR[Execute PaddleOCR / ONNX OCR]
    CheckOCR -->|Yes| Merge[BBox Alignment & Reading Order Sort]
    OCR --> Merge
    
    Merge --> TSR{Region == Table?}
    TSR -->|Yes| TableRecognizer[Table Structure Recognizer TSR]
    TSR -->|No| Formatter[Format Paragraphs & Sections]
    TableRecognizer --> Formatter
```

### Source File References
- Python PDF Parser: [deepdoc/parser/pdf_parser.py](file:///home/logan78/Desktop/ragflow/deepdoc/parser/pdf_parser.py#L35)
- Go PDF Engine: [internal/deepdoc/parser/pdf/parser.go](file:///home/logan78/Desktop/ragflow/internal/deepdoc/parser/pdf/parser.go#L40)
- Layout Boxes & Sections: [internal/deepdoc/parser/pdf/layout/boxes_sections.go](file:///home/logan78/Desktop/ragflow/internal/deepdoc/parser/pdf/layout/boxes_sections.go#L20)
